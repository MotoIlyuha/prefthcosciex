// Session state. The refresh token also goes to Telegram CloudStorage (12.3) so a
// reinstall on another device keeps the session; the web version uses a cookie.
import { create } from "zustand";

const STORAGE_KEY = "bayt.session";

interface Stored {
  accessToken: string | null;
  refreshToken: string | null;
}

function load(): Stored {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Stored;
  } catch {
    // storage may be unavailable (private mode): start signed out
  }
  return { accessToken: null, refreshToken: null };
}

function save(value: Stored): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // not persisted: the next launch signs in again through initData
  }
}

interface AuthState extends Stored {
  setTokens: (access: string, refresh: string) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  ...load(),
  setTokens: (accessToken, refreshToken) => {
    save({ accessToken, refreshToken });
    set({ accessToken, refreshToken });
  },
  logout: () => {
    save({ accessToken: null, refreshToken: null });
    set({ accessToken: null, refreshToken: null });
  },
}));
