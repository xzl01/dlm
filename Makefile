CURDIR		= $(shell pwd)
ARCH		= $(shell uname -m)

all install clean: %:
	set -e; for d in libdlm dlm_controld dlm_tool fence; do $(MAKE) -C $$d $@; done
	rm -rf dlm.spec dlm-*.tar.gz *rpm* noarch $(ARCH)
	# clean .version only if we are within a git repo otherwise
	# we cannot regenerated the .version information
	if [ -d ".git" ]; then rm -f .version; fi

check:
	@echo $@ not supported

distcheck:
	@echo $@ not supported

# version file can only be generated within a .git checkout
.PHONY: .version
.version: clean include/version.cf
	if [ -d ".git" ]; then \
		rm -f $@-t $@; \
		relver="`git tag |grep ^dlm| sort -ur | head -n 1 | sed -e 's#dlm-##g'`"; \
		numcomm="`git log dlm-$$relver..HEAD | grep ^commit | wc -l`"; \
		alphatag="`git rev-parse --short HEAD`"; \
		rpmdate="`date "+%a %b %d %Y"`"; \
		echo relver=\"$$relver\" >> $@-t; \
		echo numcomm=\"$$numcomm\" >> $@-t; \
		echo alphatag=\"$$alphatag\" >> $@-t; \
		echo rpmdate=\"$$rpmdate\" >> $@-t; \
		chmod a-w $@-t; \
		mv $@-t $@; \
		rm -f $@-t*; \
	fi

dlm.spec: .version dlm.spec.in
	rm -f $@-t $@
	. ./.version; \
	cat $@.in | sed \
		-e "s#@relver@#$$relver#g" \
		-e "s#@rpmdate@#$$rpmdate#g" \
		-e "s#@numcomm@#$$numcomm#g" \
		-e "s#@alphatag@#$$alphatag#g" \
	> $@-t;
	# if there is no .git directory, this is a release tarball
	# drop information about number of commits and alphatag
	# from spec file.
	if [ ! -d ".git" ]; then \
		sed -i -e "s#%glo.*numcomm.*##g" $@-t; \
		sed -i -e "s#%glo.*alphatag.*##g" $@-t; \
	fi
	chmod a-w $@-t
	mv $@-t $@
	rm -f $@-t*

tarball: dlm.spec .version
	. ./.version; \
	if [ ! -d ".git" ] || [ "$(RELEASE)" = 1 ]; then \
		tarver=$$relver; \
	else \
		tarver="`echo $$relver.$$numcomm.$$alphatag`"; \
	fi; \
	touch dlm-$$tarver.tar.gz; \
	tar -zcp \
	    --transform "s/^./dlm-$$relver/" \
	    -f dlm-$$tarver.tar.gz \
	    --exclude=dlm-$$tarver.tar.gz \
	    --exclude=.git \
	    .

RPMBUILDOPTS    = --define "_sourcedir $(CURDIR)" \
		  --define "_specdir $(CURDIR)" \
		  --define "_builddir $(CURDIR)" \
		  --define "_srcrpmdir $(CURDIR)" \
		  --define "_rpmdir $(CURDIR)"

srpm: tarball dlm.spec
	rpmbuild $(RPMBUILDOPTS) --nodeps -bs dlm.spec

rpm: tarball dlm.spec
	rpmbuild $(RPMBUILDOPTS) -ba dlm.spec
