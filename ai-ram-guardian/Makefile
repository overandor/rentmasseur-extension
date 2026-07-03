APP_NAME := AI RAM Guardian
BUILD_DIR := build
DIST_DIR := dist
APP := $(BUILD_DIR)/$(APP_NAME).app
BIN := $(APP)/Contents/MacOS/guardian
SRC := guardian.mm

.PHONY: app dmg install clean check

check:
	@test -f $(SRC) || (echo "error: $(SRC) is missing. Commit the production source before building." >&2; exit 2)

app: check
	@mkdir -p "$(APP)/Contents/MacOS" "$(APP)/Contents/Resources"
	@if [ -f Info.plist ]; then cp Info.plist "$(APP)/Contents/Info.plist"; else echo "error: Info.plist missing; use scripts/create_dmg.sh for fallback plist generation." >&2; exit 2; fi
	clang++ -std=gnu++17 -O2 -Wall -Wextra -fobjc-arc \
	  -framework Cocoa -framework QuartzCore -framework IOKit \
	  $(SRC) -o "$(BIN)"
	chmod +x "$(BIN)"
	codesign --force --deep --sign - "$(APP)"
	@echo "built: $(APP)"

dmg:
	@chmod +x scripts/create_dmg.sh
	@./scripts/create_dmg.sh

install: app
	@rm -rf "/Applications/$(APP_NAME).app"
	@cp -R "$(APP)" "/Applications/$(APP_NAME).app"
	@echo "installed: /Applications/$(APP_NAME).app"

clean:
	@rm -rf "$(BUILD_DIR)" "$(DIST_DIR)"
