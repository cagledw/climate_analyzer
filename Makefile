# Makefile for climate_analyzer
#   Automate packaging & virtual environment management
#   Make is far from the idea tool for this!
#
#   Build Artifacts are stored in ./dist/*
#     src distribution (dist) = *.tar.gz
#     built distribution (wheel) = *.whl
#
#   Virtual Environment in ./venv/*
#     Command Line tool *.exe in ./venv/Scripts
#
##########################################################

define venvbat
py -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
endef

PKG  = climate_analyzer
HPKG = $(subst _,-,$(PKG))
SRC  = ./src/$(PKG)
VPKG = venv\Lib\site-packages\climate_analyzer 

DISTOK = $(shell if [ -d './dist' ]; then echo 1; else echo 0; fi)
ifeq ($(DISTOK), 1)
GZFILE = $(shell find './dist' -name '*.gz')
else
GZFILE = 
endif

clean:
	rm -r -f dist
	rm -r -f venv
	rm -f $(SRC)/*.ini
	rm -r -f $(HPKG)

noinst:
	rm -r -f $(VPKG) 

# Create Virtual Environment
venv:
	hatch env create venv
	rm -r -f $(HPKG)
	
# Create Package Distribution
dist:
	@rm -f src\climte_analyzer\*.ini 
	@rm -r -f venv
	@py -m build

$(VPKG): dist venv
	@echo $(GZFILE)

# Install package in Virtual Environment
instpkg: $(VPKG)
ifeq ($(words $(GZFILE)),1)
	@$(file >$@.bat,call venv\Scripts\activate)
	@$(file >>$@.bat,pip install $(GZFILE))
	@$@.bat
	@rm -f $@.bat
endif

upld:
	twine upload dist/*

help:
	@echo venv    - Create Virtual Environment venv
	@echo dist    - Create Distrubution Folder dist
	@echo instpkg - Install $(PKG) into Virtual Env
	@echo sdist = $(GZFILE)
	@echo $(HPKG)
	# @$(file >$@.bat$^,$(venvbat))
	# @$@.bat
	# @rm -f $@.bat
