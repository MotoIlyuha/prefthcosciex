// Telegram Mini App integration (design doc 11.10). Every call is guarded: outside
// Telegram (the web version, tests) the functions quietly do nothing.
import {
  backButton,
  bindMiniAppCssVars,
  bindThemeParamsCssVars,
  bindViewportCssVars,
  closingBehavior,
  cloudStorage,
  expandViewport,
  hapticFeedback,
  init,
  isTMA,
  mainButton,
  miniAppReady,
  mountMiniApp,
  mountThemeParams,
  mountViewport,
  openTelegramLink,
  retrieveLaunchParams,
  retrieveRawInitData,
  shareURL,
  swipeBehavior,
} from "@telegram-apps/sdk";

let inTelegram = false;

function attempt(fn: () => unknown): void {
  try {
    fn();
  } catch {
    // An older Telegram client lacks the method: the feature degrades silently.
  }
}

export function initTelegram(): boolean {
  try {
    inTelegram = isTMA();
  } catch {
    inTelegram = false;
  }
  if (!inTelegram) return false;
  init();
  attempt(() => mountMiniApp.ifAvailable());
  attempt(() => mountThemeParams.ifAvailable());
  attempt(() => bindThemeParamsCssVars.ifAvailable());
  attempt(() => bindMiniAppCssVars.ifAvailable());
  attempt(() => backButton.mount.ifAvailable());
  attempt(() => mainButton.mount.ifAvailable());
  attempt(() => closingBehavior.mount.ifAvailable());
  attempt(() => swipeBehavior.mount.ifAvailable());
  attempt(() => swipeBehavior.disableVertical.ifAvailable());
  void (async () => {
    try {
      if (mountViewport.isAvailable()) {
        await mountViewport();
        bindViewportCssVars.ifAvailable();
      }
      expandViewport.ifAvailable();
    } catch {
      // viewport is cosmetic
    }
  })();
  attempt(() => miniAppReady.ifAvailable());
  return true;
}

export function isTelegram(): boolean {
  return inTelegram;
}

export function rawInitData(): string | undefined {
  if (!inTelegram) return undefined;
  try {
    return retrieveRawInitData();
  } catch {
    return undefined;
  }
}

/** Deep-link target: `startapp` from Telegram, or `?startapp=` in a plain URL. */
export function startParam(): string | undefined {
  if (inTelegram) {
    try {
      const value = retrieveLaunchParams().tgWebAppStartParam;
      if (value) return value;
    } catch {
      // fall through to the URL
    }
  }
  const fromUrl = new URLSearchParams(window.location.search).get("startapp");
  return fromUrl ?? undefined;
}

export function haptic(kind: "success" | "error" | "warning" | "light"): void {
  if (!inTelegram) return;
  attempt(() => {
    if (kind === "light") hapticFeedback.impactOccurred.ifAvailable("light");
    else hapticFeedback.notificationOccurred.ifAvailable(kind);
  });
}

export function setClosingConfirmation(enabled: boolean): void {
  if (!inTelegram) return;
  attempt(() =>
    enabled
      ? closingBehavior.enableConfirmation.ifAvailable()
      : closingBehavior.disableConfirmation.ifAvailable(),
  );
}

export function showBackButton(onClick: () => void): () => void {
  if (!inTelegram) return () => undefined;
  attempt(() => backButton.show.ifAvailable());
  let off: (() => void) | undefined;
  attempt(() => {
    const result = backButton.onClick.ifAvailable(onClick);
    if (result[0]) off = result[1];
  });
  return () => {
    off?.();
    attempt(() => backButton.hide.ifAvailable());
  };
}

export interface MainButtonSpec {
  text: string;
  enabled?: boolean;
  loading?: boolean;
  onClick: () => void;
}

/** Shows Telegram's MainButton; returns a cleanup. `false` outside Telegram. */
export function applyMainButton(spec: MainButtonSpec | null): (() => void) | false {
  if (!inTelegram || spec === null) return false;
  attempt(() =>
    mainButton.setParams.ifAvailable({
      text: spec.text,
      isVisible: true,
      isEnabled: spec.enabled ?? true,
      isLoaderVisible: spec.loading ?? false,
    }),
  );
  let off: (() => void) | undefined;
  attempt(() => {
    const result = mainButton.onClick.ifAvailable(spec.onClick);
    if (result[0]) off = result[1];
  });
  return () => {
    off?.();
    attempt(() => mainButton.setParams.ifAvailable({ isVisible: false }));
  };
}

export function share(url: string, text: string): void {
  if (inTelegram) {
    attempt(() => shareURL.ifAvailable(url, text));
    return;
  }
  if (navigator.share) void navigator.share({ url, text }).catch(() => undefined);
  else void navigator.clipboard?.writeText(url);
}

export function openTelegram(url: string): void {
  if (inTelegram) attempt(() => openTelegramLink.ifAvailable(url));
  else window.open(url, "_blank", "noopener");
}

export async function cloudGet(key: string): Promise<string | undefined> {
  if (!inTelegram || !cloudStorage.getItem.isAvailable()) return undefined;
  try {
    const value = await cloudStorage.getItem(key);
    return value || undefined;
  } catch {
    return undefined;
  }
}

export async function cloudSet(key: string, value: string): Promise<void> {
  if (!inTelegram || !cloudStorage.setItem.isAvailable()) return;
  try {
    await cloudStorage.setItem(key, value);
  } catch {
    // the refresh token simply is not persisted across devices
  }
}
