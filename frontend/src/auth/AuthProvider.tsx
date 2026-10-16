import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { config, isFirebaseConfigured } from "../config/env";
import { setTokenProvider } from "../lib/api";
import { getFirebaseAuth } from "../lib/firebase";
import { readStorage, writeStorage } from "../lib/storage";
import { AuthContext, type AuthContextValue, type AuthUser } from "./context";

const DEV_EMAIL_KEY = "share-market.dev-email";

function devUser(email: string): AuthUser {
  return { uid: `dev:${email}`, email, displayName: email.split("@")[0], photoURL: null, isDev: true };
}

function initialDevUser(): AuthUser | null {
  if (!config.authDevMode) return null;
  const email = readStorage(DEV_EMAIL_KEY);
  return email ? devUser(email) : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(initialDevUser);
  const [loading, setLoading] = useState(isFirebaseConfigured && !initialDevUser());
  const userRef = useRef(user);
  userRef.current = user;

  useEffect(() => {
    if (!isFirebaseConfigured) return;
    return onAuthStateChanged(getFirebaseAuth(), (firebaseUser) => {
      if (firebaseUser) {
        setUser({
          uid: firebaseUser.uid,
          email: firebaseUser.email,
          displayName: firebaseUser.displayName,
          photoURL: firebaseUser.photoURL,
          isDev: false,
        });
      } else if (!userRef.current?.isDev) {
        setUser(null);
      }
      setLoading(false);
    });
  }, []);

  const getToken = useCallback(async (): Promise<string | null> => {
    const current = userRef.current;
    if (!current) return null;
    if (current.isDev) return `dev:${current.email}`;
    // Firebase refreshes the token automatically when it is about to expire.
    return (await getFirebaseAuth().currentUser?.getIdToken()) ?? null;
  }, []);

  // Set during render (not in an effect): child components' queries run their effects
  // before ours, and they must already be able to attach the login token.
  setTokenProvider(getToken);

  const signInWithGoogle = useCallback(async () => {
    await signInWithPopup(getFirebaseAuth(), new GoogleAuthProvider());
  }, []);

  const signInDev = useCallback((email: string) => {
    const normalized = email.trim().toLowerCase();
    writeStorage(DEV_EMAIL_KEY, normalized);
    setUser(devUser(normalized));
  }, []);

  const signOut = useCallback(async () => {
    writeStorage(DEV_EMAIL_KEY, null);
    if (isFirebaseConfigured) await firebaseSignOut(getFirebaseAuth());
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, signInWithGoogle, signInDev, signOut, getToken }),
    [user, loading, signInWithGoogle, signInDev, signOut, getToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
