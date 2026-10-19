import { toast } from "sonner";

import { useAuth } from "../auth/context";
import type { usePushNotifications } from "../hooks/usePushNotifications";
import { playAlertSound, setSoundOn, useSoundOn } from "../lib/sound";
import { otherTheme, setTheme, useTheme } from "../lib/theme";
import {
  BellIcon,
  BellOffIcon,
  LogOutIcon,
  MoonIcon,
  SunIcon,
  VolumeIcon,
  VolumeOffIcon,
} from "./icons";

type Push = ReturnType<typeof usePushNotifications>;

function SoundToggle() {
  const on = useSoundOn();
  const label = on
    ? "Alert sounds on: ting = high alert, ting ting = low alert (click to mute)"
    : "Alert sounds off (click to turn on)";
  const toggle = () => {
    setSoundOn(!on);
    if (!on) playAlertSound("above"); // a preview, so the user hears it works
  };
  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
      title={label}
      aria-label={label}
      aria-pressed={on}
    >
      {on ? <VolumeIcon /> : <VolumeOffIcon />}
    </button>
  );
}

function ThemeToggle() {
  const { theme, dark } = useTheme();
  const label = dark ? "Switch to light mode" : "Switch to dark mode";
  return (
    <button
      type="button"
      onClick={() => setTheme(otherTheme(theme))}
      className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
      title={label}
      aria-label={label}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

const PILL = "inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm";

function NotificationControl({ push }: { push: Push }) {
  const explain = (title: string, description: string) => () => toast.info(title, { description });

  const onEnable = async () => {
    try {
      const enabled = await push.enable();
      if (enabled) toast.success("Notifications on", { description: "Alerts will reach this browser." });
    } catch (error) {
      toast.error("Couldn't turn on notifications", { description: (error as Error).message });
    }
  };

  const onTest = async () => {
    try {
      const result = await push.sendTest();
      if (result.delivered > 0) {
        toast.success("Test sent", { description: `Delivered to ${result.delivered} device(s).` });
      } else {
        toast.error("Test not delivered", { description: result.error ?? "No devices registered." });
      }
    } catch (error) {
      toast.error("Test failed", { description: (error as Error).message });
    }
  };

  switch (push.state) {
    case "checking":
      return null;
    case "not-configured":
      return (
        <button
          type="button"
          className={`${PILL} text-muted`}
          onClick={explain(
            "Push notifications aren't set up",
            "Add your Firebase web config and VAPID key to .env (see README). Alerts still show inside the app.",
          )}
        >
          <BellOffIcon /> <span className="hidden sm:inline">Push not set up</span>
        </button>
      );
    case "unsupported":
      return (
        <button
          type="button"
          className={`${PILL} text-muted`}
          onClick={explain(
            "This browser can't receive push notifications",
            "Try Chrome, Edge or Firefox. On iPhone, add this site to your Home Screen first.",
          )}
        >
          <BellOffIcon /> <span className="hidden sm:inline">Push unsupported</span>
        </button>
      );
    case "denied":
      return (
        <button
          type="button"
          className={`${PILL} text-warn`}
          onClick={explain(
            "Notifications are blocked",
            "Click the lock icon in the address bar and allow notifications for this site.",
          )}
        >
          <BellOffIcon /> <span className="hidden sm:inline">Blocked</span>
        </button>
      );
    case "off":
      return (
        <button
          type="button"
          onClick={onEnable}
          disabled={push.busy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-60"
        >
          <BellIcon /> <span className="hidden sm:inline">Enable notifications</span>
        </button>
      );
    case "on":
      return (
        <details className="relative">
          <summary className={`${PILL} cursor-pointer list-none text-up`}>
            <BellIcon /> <span className="hidden sm:inline">Notifications on</span>
          </summary>
          <div className="card absolute right-0 z-20 mt-2 w-56 p-1 shadow-lg">
            <button type="button" onClick={onTest} className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-surface-2">
              Send test notification
            </button>
            <button
              type="button"
              onClick={() => push.disable()}
              disabled={push.busy}
              className="w-full rounded-md px-3 py-2 text-left text-sm text-down hover:bg-surface-2"
            >
              Turn off on this device
            </button>
          </div>
        </details>
      );
  }
}

function UserMenu() {
  const { user, signOut } = useAuth();
  if (!user) return null;
  const label = user.displayName || user.email || "Account";
  return (
    <details className="relative">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-surface-2">
        {user.photoURL ? (
          <img src={user.photoURL} alt="" className="h-8 w-8 rounded-full" referrerPolicy="no-referrer" />
        ) : (
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-fg">
            {label.charAt(0).toUpperCase()}
          </span>
        )}
        <span className="hidden max-w-40 truncate text-sm md:inline">{label}</span>
      </summary>
      <div className="card absolute right-0 z-20 mt-2 w-60 p-1 shadow-lg">
        <div className="px-3 py-2 text-sm">
          <p className="truncate font-medium">{label}</p>
          {user.email && <p className="truncate text-xs text-muted">{user.email}</p>}
          {user.isDev && <p className="mt-1 text-xs text-warn">Dev login</p>}
        </div>
        <button
          type="button"
          onClick={() => signOut()}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-surface-2"
        >
          <LogOutIcon /> Sign out
        </button>
      </div>
    </details>
  );
}

export default function Header({ push }: { push: Push }) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/85 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <span className="font-semibold">NIFTY 50 Alerts</span>
        </div>
        <div className="flex items-center gap-2">
          <SoundToggle />
          <ThemeToggle />
          <NotificationControl push={push} />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
