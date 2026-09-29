with open('frontend/src/components/DashboardLayout.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('import { ThemeToggle } from "./ThemeToggle";', 'import { ThemeToggle } from "./ThemeToggle";\nimport { NotificationBell } from "./NotificationBell";')

old_nav = '''            <button
              id="tour-help-btn"
              onClick={() => setIsHelpOpen(true)}
              className="hidden xl:inline-flex p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted/60 transition-colors cursor-pointer min-h-[36px] min-w-[36px] items-center justify-center"
              title="Keyboard Shortcuts & Help (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            {/* Theme Toggle */}
            <ThemeToggle />'''

new_nav = '''            <button
              id="tour-help-btn"
              onClick={() => setIsHelpOpen(true)}
              className="hidden xl:inline-flex p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted/60 transition-colors cursor-pointer min-h-[36px] min-w-[36px] items-center justify-center"
              title="Keyboard Shortcuts & Help (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            {/* Notifications */}
            <NotificationBell />

            {/* Theme Toggle */}
            <ThemeToggle />'''

if old_nav in text:
    text = text.replace(old_nav, new_nav)
    with open('frontend/src/components/DashboardLayout.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Updated DashboardLayout')
else:
    print('Could not find nav replacement block')
