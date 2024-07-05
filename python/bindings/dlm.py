from enum import IntEnum, IntFlag
import sys, os, errno, platform
import ctypes, ctypes.util

#bindings

if platform.system() != "Linux":
	sys.exit("Not supported")

c_path_libdlm = ctypes.util.find_library("dlm_lt")
if not c_path_libdlm:
	print("Unable to find the specified library.")
	sys.exit()

try:
	c_libdlm = ctypes.CDLL(c_path_libdlm)
except OSError:
	print("Unable to load the system C library")
	sys.exit()

class C_DLM_LSHANDLE(ctypes.c_void_p):
	pass

class C_DLM_LKSB(ctypes.Structure):
	_fields_ = [('sb_status', ctypes.c_int),
		    ('sb_lkid', ctypes.c_uint32),
		    ('sb_flags', ctypes.c_char),
		    ('sb_lvbptr', ctypes.c_char_p)]

C_BAST_CB = ctypes.CFUNCTYPE(None, ctypes.py_object)

#dlm_create_lockspace
c_dlm_create_lockspace = c_libdlm.dlm_create_lockspace
c_dlm_create_lockspace.argtypes = [ctypes.c_char_p, #name
				   ctypes.c_uint, #mode
				  ]
c_dlm_create_lockspace.restype = C_DLM_LSHANDLE

#dlm_release_lockspace
c_dlm_release_lockspace = c_libdlm.dlm_release_lockspace
c_dlm_release_lockspace.argtypes = [ctypes.c_char_p, #name
				    C_DLM_LSHANDLE, #ls
				    ctypes.c_int, #force
				   ]
c_dlm_release_lockspace.restype = ctypes.c_int

#dlm_ls_lock_wait
c_dlm_ls_lock_wait = c_libdlm.dlm_ls_lock_wait
c_dlm_ls_lock_wait.argtypes = [C_DLM_LSHANDLE, #ls
			       ctypes.c_uint32, #mode
			       ctypes.POINTER(C_DLM_LKSB), #lksb
			       ctypes.c_uint32, #flags
			       ctypes.c_char_p, #name
			       ctypes.c_uint, #namelen
			       ctypes.c_uint32, #parent
			       ctypes.py_object, #bastarg
			       C_BAST_CB, #bastaddr
			       ctypes.c_void_p, #range
			      ]
c_dlm_ls_lock_wait.restype = ctypes.c_int

#dlm_ls_unlock_wait
c_dlm_ls_unlock_wait = c_libdlm.dlm_ls_unlock_wait
c_dlm_ls_unlock_wait.argtypes = [C_DLM_LSHANDLE, #ls
				 ctypes.c_uint32, #lkid
				 ctypes.c_uint32, #flags
				 ctypes.POINTER(C_DLM_LKSB), #lksb
				]
c_dlm_ls_unlock_wait.restype = ctypes.c_int

#classes

class LockMode(IntEnum):
	IV = -1
	NL = 0
	CR = 1
	CW = 2
	PR = 3
	PW = 4
	EX = 5

class LockFlag(IntFlag):
	NOQUEUE = 0x00000001
	CANCEL = 0x00000002
	CONVERT = 0x00000004
	VALBLK = 0x00000008
	QUECVT = 0x00000010
	IVVALBLK = 0x00000020
	CONVDEADLK = 0x00000040
	PERSISTENT = 0x00000080
	NODLCKWT = 0x00000100
	NODLCKBLK = 0x00000200
	EXPEDITE = 0x00000400
	NOQUEUEBAST = 0x00000800
	HEADQUE = 0x00001000
	NOORDER = 0x00002000
	ORPHAN = 0x00004000
	ALTPR = 0x00008000
	ALTCW = 0x00010000
	FORCEUNLOCK = 0x00020000
	TIMEOUT = 0x00040000

class LockSBFlag(IntFlag):
	DEMOTED = 0x01
	VALNOTVALID = 0x02
	ALTMODE = 0x04

class DLMError(OSError):

	def __init__(self, errno):
		if not errno < 0:
			raise ValueError()

		errno = abs(errno)
		super().__init__(errno, os.strerror(errno))

DLM_LOCK_TO_STR_FORMAT = \
"""name: {}
last_mode: {}
last_flags: {}
local_locked: {}
last_sb: status: {}, lkid: {}, flags: {}, lvb: {}"""

class Lockspace:

	def __init__(self, name="default", mode=0o600):
		self.__lsname = name
		self.__ls = c_dlm_create_lockspace(self.__lsname.encode(), mode)
		if not self.__ls:
			raise DLMError(-errno.ENOMEM)

	def release(self, force=2):
		if not self.__ls:
			return

		rc = c_dlm_release_lockspace(self.__lsname.encode(), self.__ls,
					     force)
		if rc:
			raise DLMError(rc)

		self.__ls = None

	def __del__(self):
		self.release()

	def __str__(self):
		return "Lockspace: {}".format(self.__lsname)

	def get_name(self):
		return self.__lsname

	# lockspace lock factory
	def create_lock(self, name):
		class Lock:

			#note name should be 8 byte aligned for now
			def __init__(self, ls, c_ls, name):
				self.__local_locked = False
				self.__last_mode = LockMode.IV
				self.__last_flags = LockFlag(0)

				self.__lk = C_DLM_LKSB()
				self.__lk.sb_status = 0
				self.__lk.sb_lkid = 0
				self.__lk.sb_flags = LockSBFlag(0)
				self.__lk.sb_lvbptr = None

				self.__ls = ls
				self.__c_ls = c_ls
				self.__name = name

			def __del__(self):
				if self.__local_locked:
					self.unlock_wait()

			def __str__(self):
				sb = self.get_sb()
				return DLM_LOCK_TO_STR_FORMAT.format(
						self.__name,
						str(self.__last_mode),
						str(self.__last_flags),
						self.__local_locked,
						str(sb.status),
						sb.lkid, str(sb.flags),
						str(sb.lvb))

			def get_name(self):
				return self.__name

			def get_ls(self):
				return self.__ls

			# get a copy of current sb state in high-level python
			def get_sb(self):
				class LockSB:

					def __init__(self, status, lkid,
						     flags, lvb):
						self.status = status
						self.lkid = lkid
						self.flags = LockSBFlag(flags[0])
						self.lvb = lvb

				return LockSB(self.__lk.sb_status,
					      self.__lk.sb_lkid,
					      self.__lk.sb_flags,
					      self.__lk.sb_lvbptr)

			def lock_wait(self, mode=LockMode.EX,
				      flags=LockFlag(0), bast=None,
				      bastarg=None):
				if bast:
					bast = C_BAST_CB(bast)
				else:
					bast = ctypes.cast(None, C_BAST_CB)

				rc = c_dlm_ls_lock_wait(self.__c_ls, mode,
							ctypes.byref(self.__lk),
							flags,
							self.__name.encode(),
							len(self.__name), 0,
							bastarg, bast, None)
				if rc:
					raise DLMError(rc)

				self.__last_mode = mode
				self.__last_flags = flags
				self.__local_locked = True

			def unlock_wait(self, flags=0):
				rc = c_dlm_ls_unlock_wait(self.__c_ls,
							  self.__lk.sb_lkid,
							  flags,
							  ctypes.byref(self.__lk))
				if rc:
					raise DLMError(rc)

				self.__last_flags = flags
				self.__local_locked = False

		lock = Lock(self, self.__ls, name)
		return lock

# vim: tabstop=8 softtabstop=8 shiftwidth=8 noexpandtab
