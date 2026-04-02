# WattWise Mobile App — Architecture & Implementation Plan

## Table of Contents

1. [Project Setup](#1-project-setup)
2. [Data Layer](#2-data-layer)
3. [Authentication](#3-authentication)
4. [API Clients](#4-api-clients)
5. [UI & Navigation](#5-ui--navigation)
6. [Build & Deploy](#6-build--deploy)
7. [Migration Path](#7-migration-path)

---

## 1. Project Setup

### Expo (Managed Workflow) — Recommended

Use **Expo SDK 52+** with the managed workflow. The reasons:

- **No native code required initially.** All APIs WattWise calls (Supabase REST, ClearBlade REST) are standard HTTPS. MQTT can be handled via a JS library (MQTT.js over WebSocket) without native modules.
- **EAS Build** handles iOS/Android compilation without local Xcode/Android Studio.
- **Over-the-air updates** via `expo-updates` — ship bug fixes without App Store review.
- **Escape hatch exists.** If a native module is needed later (e.g., `react-native-tcp-socket` for Kasa local control), run `npx expo prebuild` to eject to bare workflow at any time.

If Kasa local-network UDP/TCP control is a launch requirement, start with **Expo bare workflow** (prebuild) from day one instead.

### Project Initialization

```bash
npx create-expo-app@latest wattwise --template blank-typescript
cd wattwise
npx expo install expo-router expo-secure-store expo-sqlite expo-font expo-constants expo-linking
```

### Project Structure

```
wattwise/
├── app/                          # Expo Router (file-based routing)
│   ├── _layout.tsx               # Root layout (auth gate + providers)
│   ├── (auth)/                   # Auth group (no tab bar)
│   │   ├── _layout.tsx
│   │   ├── login.tsx
│   │   └── signup.tsx
│   ├── (tabs)/                   # Main app (tab bar)
│   │   ├── _layout.tsx           # Tab navigator config
│   │   ├── index.tsx             # Dashboard tab
│   │   ├── devices/
│   │   │   ├── index.tsx         # Device list
│   │   │   └── [id].tsx          # Device detail/control
│   │   ├── optimize.tsx          # Schedule optimizer
│   │   ├── history.tsx           # Energy history + charts
│   │   └── settings.tsx          # Account, TOU rates, preferences
│   └── +not-found.tsx
├── src/
│   ├── components/               # Shared UI components
│   │   ├── ui/                   # Primitives (Button, Card, Input, etc.)
│   │   ├── charts/               # Chart wrappers
│   │   ├── device/               # DeviceCard, ModeSelector, TempSlider
│   │   └── layout/               # SafeArea, Header, TabBar overrides
│   ├── services/                 # External API clients
│   │   ├── supabase.ts           # Supabase client singleton
│   │   ├── econet.ts             # ClearBlade REST client (ported from Python)
│   │   ├── econet-mqtt.ts        # MQTT.js WebSocket client for real-time
│   │   └── kasa.ts               # Kasa cloud API (local requires native)
│   ├── stores/                   # Zustand stores
│   │   ├── auth.ts               # Auth state + token management
│   │   ├── devices.ts            # Device list + current state
│   │   ├── energy.ts             # Energy/water usage data
│   │   ├── schedule.ts           # Schedule entries
│   │   ├── tou-rates.ts          # TOU rate tiers (cached)
│   │   └── preferences.ts        # Comfort preferences
│   ├── db/                       # Local SQLite layer
│   │   ├── schema.ts             # Table definitions (mirrors models.py)
│   │   ├── migrations.ts         # Schema version migrations
│   │   ├── queries.ts            # Typed query functions
│   │   └── sync.ts               # Bidirectional Supabase sync engine
│   ├── hooks/                    # Custom React hooks
│   │   ├── useDevice.ts
│   │   ├── useEnergy.ts
│   │   ├── useSync.ts
│   │   └── useNetworkStatus.ts
│   ├── utils/                    # Pure helpers
│   │   ├── dates.ts
│   │   ├── energy-calc.ts        # Cost calculations, TOU matching
│   │   └── constants.ts
│   └── theme/                    # Design tokens, dark/light themes
│       ├── colors.ts
│       ├── spacing.ts
│       └── index.ts
├── assets/                       # Fonts, images, app icon
├── app.json                      # Expo config
├── eas.json                      # EAS Build profiles
├── tsconfig.json
└── package.json
```

### Core Dependencies

```json
{
  "dependencies": {
    "expo": "~52.0.0",
    "expo-router": "~4.0.0",
    "expo-secure-store": "~14.0.0",
    "expo-sqlite": "~15.0.0",
    "expo-constants": "~17.0.0",
    "expo-linking": "~7.0.0",
    "expo-font": "~13.0.0",
    "expo-updates": "~0.27.0",
    "expo-notifications": "~0.29.0",
    "expo-haptics": "~14.0.0",
    "react-native": "0.76.x",
    "react-native-reanimated": "~3.16.0",
    "react-native-gesture-handler": "~2.20.0",
    "react-native-safe-area-context": "~4.12.0",
    "react-native-screens": "~4.4.0",

    "@supabase/supabase-js": "^2.45.0",
    "zustand": "^5.0.0",
    "mqtt": "^5.10.0",
    "date-fns": "^4.1.0",
    "victory-native": "^41.0.0",
    "@shopify/react-native-skia": "^1.5.0",
    "@react-native-async-storage/async-storage": "^2.1.0",
    "react-native-mmkv": "^3.2.0"
  },
  "devDependencies": {
    "typescript": "~5.6.0",
    "@types/react": "~18.3.0",
    "jest": "^29.7.0",
    "@testing-library/react-native": "^12.9.0"
  }
}
```

---

## 2. Data Layer

### State Management: Zustand

Zustand over Redux Toolkit or Jotai because:
- Minimal boilerplate for a mid-size app
- Works seamlessly with React Native and expo-sqlite
- Easy persistence via middleware
- No provider wrappers needed

#### Auth Store Pattern

```typescript
// src/stores/auth.ts
import { create } from 'zustand';
import { supabase } from '../services/supabase';
import * as SecureStore from 'expo-secure-store';

interface AuthState {
  session: Session | null;
  user: User | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signInWithMagicLink: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  restoreSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  session: null,
  user: null,
  isLoading: true,

  signIn: async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    set({ session: data.session, user: data.user });
  },

  signUp: async (email, password) => {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    set({ session: data.session, user: data.user });
  },

  signInWithMagicLink: async (email) => {
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: 'wattwise://auth/callback' },
    });
    if (error) throw error;
  },

  signOut: async () => {
    await supabase.auth.signOut();
    set({ session: null, user: null });
  },

  restoreSession: async () => {
    const { data } = await supabase.auth.getSession();
    set({ session: data.session, user: data.session?.user ?? null, isLoading: false });
  },
}));
```

#### Device Store Pattern

```typescript
// src/stores/devices.ts
import { create } from 'zustand';
import { EcoNetClient } from '../services/econet';
import { db } from '../db/queries';

interface DeviceState {
  devices: WaterHeaterState[];
  selectedDeviceId: string | null;
  isPolling: boolean;
  econetClient: EcoNetClient | null;

  initEcoNet: (email: string, password: string) => Promise<void>;
  refreshDevices: () => Promise<void>;
  setSetpoint: (deviceId: string, temp: number) => Promise<boolean>;
  setMode: (deviceId: string, mode: string) => Promise<boolean>;
  selectDevice: (id: string) => void;
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  devices: [],
  selectedDeviceId: null,
  isPolling: false,
  econetClient: null,

  initEcoNet: async (email, password) => {
    const client = new EcoNetClient(email, password);
    const success = await client.login();
    if (!success) throw new Error('EcoNet login failed');
    set({ econetClient: client });
    await get().refreshDevices();
  },

  refreshDevices: async () => {
    const client = get().econetClient;
    if (!client) return;
    const equipment = await client.getEquipment();
    set({ devices: equipment });
    // Persist to local DB
    await db.upsertDevices(equipment);
  },

  setSetpoint: async (deviceId, temp) => {
    const client = get().econetClient;
    if (!client) return false;
    const ok = await client.setSetpoint(deviceId, temp);
    if (ok) await get().refreshDevices();
    return ok;
  },

  setMode: async (deviceId, mode) => {
    const client = get().econetClient;
    if (!client) return false;
    const ok = await client.setMode(deviceId, mode);
    if (ok) await get().refreshDevices();
    return ok;
  },

  selectDevice: (id) => set({ selectedDeviceId: id }),
}));
```

### Local Storage: expo-sqlite + MMKV

Two-tier local storage:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Structured data** | `expo-sqlite` (synchronous API, SDK 52+) | Energy history, device state, schedules, TOU rates |
| **Key-value cache** | `react-native-mmkv` | Preferences, sync timestamps, feature flags, small JSON blobs |

**Why not WatermelonDB?** WatermelonDB adds significant complexity (model classes, decorators, lazy loading) that is overkill for this data volume. WattWise has at most a few thousand energy rows per year per device. `expo-sqlite` with direct SQL is simpler, faster to develop, and has zero native dependencies in Expo SDK 52+.

#### SQLite Schema (mirrors models.py)

```typescript
// src/db/schema.ts
export const SCHEMA_VERSION = 1;

export const CREATE_TABLES = `
  CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'econet',
    device_type TEXT NOT NULL DEFAULT 'water_heater',
    external_device_id TEXT,
    serial_number TEXT,
    device_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_state_json TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS energy_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    date TEXT NOT NULL,
    hour INTEGER NOT NULL,
    kwh REAL NOT NULL,
    cost REAL,
    tou_rate REAL,
    tou_tier TEXT,
    synced INTEGER NOT NULL DEFAULT 0,
    UNIQUE(device_id, date, hour)
  );

  CREATE TABLE IF NOT EXISTS daily_energy_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    date TEXT NOT NULL,
    total_kwh REAL NOT NULL,
    total_cost REAL NOT NULL,
    peak_kwh REAL NOT NULL DEFAULT 0,
    mid_peak_kwh REAL NOT NULL DEFAULT 0,
    off_peak_kwh REAL NOT NULL DEFAULT 0,
    peak_cost REAL NOT NULL DEFAULT 0,
    mid_peak_cost REAL NOT NULL DEFAULT 0,
    off_peak_cost REAL NOT NULL DEFAULT 0,
    synced INTEGER NOT NULL DEFAULT 0,
    UNIQUE(device_id, date)
  );

  CREATE TABLE IF NOT EXISTS heater_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    setpoint REAL NOT NULL,
    current_temp REAL,
    hot_water_avail REAL,
    mode TEXT NOT NULL,
    running INTEGER NOT NULL,
    running_state TEXT,
    synced INTEGER NOT NULL DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS schedule_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL DEFAULT '',
    day_of_week INTEGER NOT NULL DEFAULT 0,
    time_of_day TEXT NOT NULL,
    setpoint REAL NOT NULL,
    mode TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    synced INTEGER NOT NULL DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS tou_rate_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_hour INTEGER NOT NULL,
    end_hour INTEGER NOT NULL,
    rate_per_kwh REAL NOT NULL,
    days_of_week TEXT NOT NULL,
    holiday_exception INTEGER NOT NULL DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS comfort_preferences (
    id INTEGER PRIMARY KEY DEFAULT 1,
    min_acceptable_temp REAL NOT NULL DEFAULT 110.0,
    max_recovery_minutes INTEGER NOT NULL DEFAULT 60,
    preferred_setpoint REAL NOT NULL DEFAULT 120.0,
    away_setpoint REAL
  );

  CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    last_synced_at TEXT NOT NULL,
    rows_pushed INTEGER NOT NULL DEFAULT 0,
    rows_pulled INTEGER NOT NULL DEFAULT 0,
    error TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_energy_date ON energy_usage(date);
  CREATE INDEX IF NOT EXISTS idx_energy_device ON energy_usage(device_id);
  CREATE INDEX IF NOT EXISTS idx_readings_ts ON heater_readings(timestamp);
  CREATE INDEX IF NOT EXISTS idx_readings_device ON heater_readings(device_id);
`;
```

#### Database Initialization

```typescript
// src/db/queries.ts
import * as SQLite from 'expo-sqlite';
import { CREATE_TABLES } from './schema';

let _db: SQLite.SQLiteDatabase | null = null;

export function getDb(): SQLite.SQLiteDatabase {
  if (!_db) {
    _db = SQLite.openDatabaseSync('wattwise.db');
    _db.execSync(CREATE_TABLES);
  }
  return _db;
}

export const db = {
  upsertDevices: (devices: WaterHeaterState[]) => {
    const d = getDb();
    for (const dev of devices) {
      d.runSync(
        `INSERT INTO devices (id, name, serial_number, device_name, last_state_json, updated_at)
         VALUES (?, ?, ?, ?, ?, datetime('now'))
         ON CONFLICT(id) DO UPDATE SET
           name = excluded.name,
           last_state_json = excluded.last_state_json,
           updated_at = datetime('now')`,
        [dev.device_id, dev.name, dev.device_id, dev.device_name, JSON.stringify(dev)]
      );
    }
  },

  insertEnergyUsage: (deviceId: string, date: string, hour: number, kwh: number, cost?: number, touRate?: number, touTier?: string) => {
    const d = getDb();
    d.runSync(
      `INSERT INTO energy_usage (device_id, date, hour, kwh, cost, tou_rate, tou_tier)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(device_id, date, hour) DO UPDATE SET
         kwh = excluded.kwh, cost = excluded.cost,
         tou_rate = excluded.tou_rate, tou_tier = excluded.tou_tier`,
      [deviceId, date, hour, kwh, cost ?? null, touRate ?? null, touTier ?? null]
    );
  },

  getEnergyRange: (deviceId: string, startDate: string, endDate: string) => {
    const d = getDb();
    return d.getAllSync<EnergyRow>(
      `SELECT * FROM energy_usage WHERE device_id = ? AND date >= ? AND date <= ? ORDER BY date, hour`,
      [deviceId, startDate, endDate]
    );
  },

  getUnsyncedRows: (table: string, limit = 500) => {
    const d = getDb();
    return d.getAllSync(`SELECT * FROM ${table} WHERE synced = 0 LIMIT ?`, [limit]);
  },

  markSynced: (table: string, ids: number[]) => {
    if (ids.length === 0) return;
    const d = getDb();
    const placeholders = ids.map(() => '?').join(',');
    d.runSync(`UPDATE ${table} SET synced = 1 WHERE id IN (${placeholders})`, ids);
  },
};
```

### Offline Sync Strategy with Supabase

The sync engine follows a **push-primary, pull-secondary** model. The mobile app is the source of truth for data it collects (energy readings, device state snapshots). Supabase is the source of truth for shared configuration (TOU rates, user profile, locations).

#### Sync Architecture

```
Mobile App (source of truth for readings)
  |
  |-- [PUSH] energy_usage, daily_summary, heater_readings --> Supabase
  |-- [PULL] tou_rate_entries, user profile, locations     <-- Supabase
  |-- [BIDIRECTIONAL] schedule_entries, comfort_preferences <-> Supabase
```

#### Sync Engine

```typescript
// src/db/sync.ts
import NetInfo from '@react-native-community/netinfo';
import { supabase } from '../services/supabase';
import { db, getDb } from './queries';
import { MMKV } from 'react-native-mmkv';

const storage = new MMKV();

interface SyncResult {
  table: string;
  pushed: number;
  pulled: number;
  error?: string;
}

export class SyncEngine {
  private isSyncing = false;

  async syncAll(): Promise<SyncResult[]> {
    if (this.isSyncing) return [];

    const netState = await NetInfo.fetch();
    if (!netState.isConnected) return [];

    this.isSyncing = true;
    const results: SyncResult[] = [];

    try {
      // Push local changes first
      results.push(await this.pushTable('energy_usage'));
      results.push(await this.pushTable('daily_energy_summary'));
      results.push(await this.pushTable('heater_readings'));
      results.push(await this.pushTable('schedule_entries'));

      // Pull remote config
      results.push(await this.pullTOURates());
      results.push(await this.pullScheduleEntries());
    } finally {
      this.isSyncing = false;
    }

    return results;
  }

  private async pushTable(table: string): Promise<SyncResult> {
    const rows = db.getUnsyncedRows(table);
    if (rows.length === 0) return { table, pushed: 0, pulled: 0 };

    try {
      const { data, error } = await supabase
        .from(table)
        .upsert(rows.map(r => ({ ...r, user_id: supabase.auth.getUser() })), {
          onConflict: table === 'energy_usage' ? 'user_id,date,hour' : 'id',
        });

      if (error) throw error;

      const ids = rows.map((r: any) => r.id);
      db.markSynced(table, ids);

      // Record sync timestamp
      storage.set(`sync.${table}.lastPush`, new Date().toISOString());

      return { table, pushed: rows.length, pulled: 0 };
    } catch (e: any) {
      return { table, pushed: 0, pulled: 0, error: e.message };
    }
  }

  private async pullTOURates(): Promise<SyncResult> {
    const lastPull = storage.getString('sync.tou_rates.lastPull') ?? '1970-01-01';

    try {
      const { data, error } = await supabase
        .from('tou_rate_entries')
        .select('*')
        .gt('updated_at', lastPull);

      if (error) throw error;
      if (!data || data.length === 0) return { table: 'tou_rates', pushed: 0, pulled: 0 };

      const d = getDb();
      // Replace all TOU rates (they are managed server-side)
      d.runSync('DELETE FROM tou_rate_entries');
      for (const rate of data) {
        d.runSync(
          `INSERT INTO tou_rate_entries (name, start_hour, end_hour, rate_per_kwh, days_of_week, holiday_exception)
           VALUES (?, ?, ?, ?, ?, ?)`,
          [rate.name, rate.start_hour, rate.end_hour, rate.rate_per_kwh, rate.days_of_week, rate.holiday_exception ? 1 : 0]
        );
      }
      storage.set('sync.tou_rates.lastPull', new Date().toISOString());
      return { table: 'tou_rates', pushed: 0, pulled: data.length };
    } catch (e: any) {
      return { table: 'tou_rates', pushed: 0, pulled: 0, error: e.message };
    }
  }

  private async pullScheduleEntries(): Promise<SyncResult> {
    // Bidirectional: pull entries modified after our last pull
    const lastPull = storage.getString('sync.schedules.lastPull') ?? '1970-01-01';

    try {
      const { data, error } = await supabase
        .from('schedule_entries')
        .select('*')
        .gt('updated_at', lastPull);

      if (error) throw error;
      if (!data || data.length === 0) return { table: 'schedule_entries', pushed: 0, pulled: 0 };

      const d = getDb();
      for (const entry of data) {
        d.runSync(
          `INSERT INTO schedule_entries (id, device_id, day_of_week, time_of_day, setpoint, mode, is_active, source, synced)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(id) DO UPDATE SET
             setpoint = excluded.setpoint, mode = excluded.mode,
             is_active = excluded.is_active, synced = 1`,
          [entry.id, entry.device_id, entry.day_of_week, entry.time_of_day, entry.setpoint, entry.mode, entry.is_active ? 1 : 0, entry.source]
        );
      }
      storage.set('sync.schedules.lastPull', new Date().toISOString());
      return { table: 'schedule_entries', pushed: 0, pulled: data.length };
    } catch (e: any) {
      return { table: 'schedule_entries', pushed: 0, pulled: 0, error: e.message };
    }
  }
}

export const syncEngine = new SyncEngine();
```

#### Auto-Sync Triggers

```typescript
// In app/_layout.tsx — register sync on app foreground + network restore
import { AppState, AppStateStatus } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { syncEngine } from '../src/db/sync';

useEffect(() => {
  // Sync when app comes to foreground
  const sub = AppState.addEventListener('change', (state: AppStateStatus) => {
    if (state === 'active') syncEngine.syncAll();
  });

  // Sync when network is restored
  const unsub = NetInfo.addEventListener((state) => {
    if (state.isConnected) syncEngine.syncAll();
  });

  return () => { sub.remove(); unsub(); };
}, []);
```

### Supabase Realtime Subscriptions

Supabase Realtime can push changes from other devices/web to the mobile app. Use sparingly — only for config changes that affect device behavior.

```typescript
// Subscribe to schedule changes made on another device
const channel = supabase
  .channel('schedule-changes')
  .on('postgres_changes', {
    event: '*',
    schema: 'public',
    table: 'schedule_entries',
    filter: `user_id=eq.${userId}`,
  }, (payload) => {
    // Update local SQLite and Zustand store
    handleRemoteScheduleChange(payload);
  })
  .subscribe();
```

Use Realtime only when the app is in the foreground. Unsubscribe on background. Do NOT rely on Realtime for data integrity — the pull-based sync handles that.

---

## 3. Authentication

### Supabase Auth in React Native

```typescript
// src/services/supabase.ts
import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!;

// Custom storage adapter using expo-secure-store for token persistence
const ExpoSecureStoreAdapter = {
  getItem: async (key: string): Promise<string | null> => {
    return await SecureStore.getItemAsync(key);
  },
  setItem: async (key: string, value: string): Promise<void> => {
    await SecureStore.setItemAsync(key, value);
  },
  removeItem: async (key: string): Promise<void> => {
    await SecureStore.deleteItemAsync(key);
  },
};

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: ExpoSecureStoreAdapter,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false, // Handled manually via deep linking
  },
});
```

### Auth Flow

```
1. App launch
   └─> restoreSession() — checks SecureStore for persisted token
       ├─ Valid session → navigate to (tabs)
       └─ No session   → navigate to (auth)/login

2. Email/Password sign-in
   └─> supabase.auth.signInWithPassword()
       └─> Session stored in SecureStore automatically

3. Magic link sign-in
   └─> supabase.auth.signInWithOtp({ email, emailRedirectTo: 'wattwise://auth/callback' })
       └─> User clicks email link
           └─> Deep link opens app: wattwise://auth/callback#access_token=...
               └─> Parse URL fragment, call supabase.auth.setSession()

4. Token refresh
   └─> Handled automatically by @supabase/supabase-js (autoRefreshToken: true)
       └─> Refresh token stored in SecureStore, exchanged before expiry
```

### Deep Link Configuration for Magic Links

```json
// app.json
{
  "expo": {
    "scheme": "wattwise",
    "plugins": [
      ["expo-router", { "origin": "https://wattwise.app" }]
    ]
  }
}
```

```typescript
// app/(auth)/callback.tsx — handles magic link deep links
import { useEffect } from 'react';
import { useURL } from 'expo-linking';
import { router } from 'expo-router';
import { supabase } from '../../src/services/supabase';

export default function AuthCallback() {
  const url = useURL();

  useEffect(() => {
    if (!url) return;
    // Supabase puts tokens in the URL fragment
    const hashParams = new URLSearchParams(url.split('#')[1] ?? '');
    const accessToken = hashParams.get('access_token');
    const refreshToken = hashParams.get('refresh_token');

    if (accessToken && refreshToken) {
      supabase.auth.setSession({ access_token: accessToken, refresh_token: refreshToken })
        .then(() => router.replace('/(tabs)'));
    }
  }, [url]);

  return <LoadingScreen message="Signing you in..." />;
}
```

### Auth Gate (Root Layout)

```typescript
// app/_layout.tsx
import { useEffect } from 'react';
import { Slot, router, useSegments } from 'expo-router';
import { useAuthStore } from '../src/stores/auth';

export default function RootLayout() {
  const { session, isLoading, restoreSession } = useAuthStore();
  const segments = useSegments();

  useEffect(() => { restoreSession(); }, []);

  useEffect(() => {
    if (isLoading) return;
    const inAuthGroup = segments[0] === '(auth)';

    if (!session && !inAuthGroup) {
      router.replace('/(auth)/login');
    } else if (session && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [session, isLoading, segments]);

  if (isLoading) return <LoadingScreen />;
  return <Slot />;
}
```

### Secure Storage for EcoNet Credentials

EcoNet credentials (separate from Supabase auth) must be stored encrypted on-device. Use `expo-secure-store` (backed by iOS Keychain / Android Keystore).

```typescript
// src/services/credential-store.ts
import * as SecureStore from 'expo-secure-store';

const ECONET_EMAIL_KEY = 'econet_email';
const ECONET_PASSWORD_KEY = 'econet_password';

export const credentialStore = {
  saveEcoNetCredentials: async (email: string, password: string) => {
    await SecureStore.setItemAsync(ECONET_EMAIL_KEY, email);
    await SecureStore.setItemAsync(ECONET_PASSWORD_KEY, password);
  },

  getEcoNetCredentials: async (): Promise<{ email: string; password: string } | null> => {
    const email = await SecureStore.getItemAsync(ECONET_EMAIL_KEY);
    const password = await SecureStore.getItemAsync(ECONET_PASSWORD_KEY);
    if (!email || !password) return null;
    return { email, password };
  },

  clearEcoNetCredentials: async () => {
    await SecureStore.deleteItemAsync(ECONET_EMAIL_KEY);
    await SecureStore.deleteItemAsync(ECONET_PASSWORD_KEY);
  },
};
```

---

## 4. API Clients

### EcoNet ClearBlade Client (TypeScript Port)

The existing `econet_client.py` must be ported to TypeScript. The REST portion is straightforward (HTTPS calls). The MQTT portion requires a different approach.

```typescript
// src/services/econet.ts
const CB_BASE_URL = 'https://rheem.clearblade.com';
const CB_SYSTEM_KEY = 'e2e699cb0bb0bbb88fc8858cb5a401';
const CB_SYSTEM_SECRET = 'E2E699CB0BE6C6FADDB1B0BC9A20';

export interface WaterHeaterState {
  deviceId: string;       // serial_number
  deviceName: string;     // ClearBlade device ID
  name: string;
  setpoint: number;
  setpointMin: number;
  setpointMax: number;
  currentTemp: number | null;
  hotWaterAvail: number | null;
  mode: string;
  modes: string[];
  running: boolean;
  runningState: string | null;
  wifiSignal: number | null;
  connected: boolean;
  active: boolean;
  todaysEnergyKwh: number | null;
  compressorHealth: number | null;
  tankHealth: number | null;
  location: { city: string; state: string; zipcode: string } | null;
}

export class EcoNetClient {
  private userToken = '';
  private accountId = '';
  private cbUserId = '';
  private authenticated = false;
  private lastAuthTime = 0;

  constructor(
    private email: string,
    private password: string,
  ) {}

  async login(): Promise<boolean> {
    try {
      const resp = await fetch(`${CB_BASE_URL}/api/v/1/user/auth`, {
        method: 'POST',
        headers: this.cbHeaders(),
        body: JSON.stringify({ email: this.email, password: this.password }),
      });

      if (!resp.ok) return false;
      const data = await resp.json();

      this.userToken = data.user_token;
      this.accountId = data.options?.account_id ?? data.user_id ?? '';
      this.cbUserId = data.user_id ?? '';
      this.authenticated = true;
      this.lastAuthTime = Date.now();
      return true;
    } catch {
      this.authenticated = false;
      return false;
    }
  }

  async getEquipment(): Promise<WaterHeaterState[]> {
    await this.ensureAuthenticated();
    const resp = await fetch(
      `${CB_BASE_URL}/api/v/1/code/${CB_SYSTEM_KEY}/getUserDataForApp`,
      {
        method: 'POST',
        headers: this.cbHeaders(true),
        body: JSON.stringify({ resource: 'friedrich' }),
      }
    );
    const data = await resp.json();
    let results = data.results ?? data;
    if (typeof results === 'string') results = JSON.parse(results);

    const equipment: WaterHeaterState[] = [];
    const locations = results.locations ?? [];

    for (const location of locations) {
      const devices = location.equiptments ?? location.equipments ?? [];
      for (const device of devices) {
        const parsed = this.parseDevice(device, location);
        if (parsed) equipment.push(parsed);
      }
    }
    return equipment;
  }

  async setSetpoint(deviceId: string, temperature: number): Promise<boolean> {
    temperature = Math.max(110, Math.min(140, temperature));
    return this.publishDesired(deviceId, { '@SETPOINT': temperature });
  }

  async setMode(deviceId: string, mode: string): Promise<boolean> {
    const modeMap: Record<string, number> = {
      OFF: 0, ENERGY_SAVING: 1, HEAT_PUMP_ONLY: 2,
      HIGH_DEMAND: 3, ELECTRIC_MODE: 4, VACATION: 5,
    };
    const modeNum = modeMap[mode];
    if (modeNum === undefined) return false;
    return this.publishDesired(deviceId, { '@MODE': modeNum });
  }

  async getEnergyUsage(deviceName: string, serialNumber: string, start: string, end: string): Promise<Record<number, number>> {
    await this.ensureAuthenticated();
    const resp = await fetch(
      `${CB_BASE_URL}/api/v/1/code/${CB_SYSTEM_KEY}/dynamicAction`,
      {
        method: 'POST',
        headers: this.cbHeaders(true),
        body: JSON.stringify({
          ACTION: 'waterheaterUsageReportView',
          device_name: deviceName,
          serial_number: serialNumber,
          start_date: `${start}T00:00:00.999`,
          end_date: `${end}T23:59:59.999`,
          usage_type: 'energyUsage',
        }),
      }
    );
    const data = await resp.json();
    if (!data.success) return {};
    let results = data.results;
    if (typeof results === 'string') results = JSON.parse(results);
    const usage: Record<number, number> = {};
    for (const item of results?.energy_usage?.data ?? []) {
      usage[parseInt(item.name)] = parseFloat(item.value);
    }
    return usage;
  }

  // --- Private helpers (same logic as econet_client.py) ---

  private cbHeaders(authed = false): Record<string, string> {
    const h: Record<string, string> = {
      'ClearBlade-SystemKey': CB_SYSTEM_KEY,
      'ClearBlade-SystemSecret': CB_SYSTEM_SECRET,
      'Content-Type': 'application/json',
    };
    if (authed && this.userToken) {
      h['ClearBlade-UserToken'] = this.userToken;
    }
    return h;
  }

  private async ensureAuthenticated(): Promise<void> {
    const elapsed = Date.now() - this.lastAuthTime;
    if (!this.authenticated || elapsed > 25 * 60 * 1000) {
      await this.login();
    }
  }

  private async publishDesired(deviceId: string, payload: Record<string, any>): Promise<boolean> {
    await this.ensureAuthenticated();
    // Use ClearBlade REST messaging API (publishes to MQTT topic via HTTP)
    const topic = `user/${this.accountId}/device/desired`;
    const msg = {
      transactionId: `MOBILE_${new Date().toISOString()}`,
      device_name: deviceId,
      serial_number: deviceId,
      ...payload,
    };

    try {
      const resp = await fetch(`${CB_BASE_URL}/api/v/1/message/${CB_SYSTEM_KEY}`, {
        method: 'POST',
        headers: this.cbHeaders(true),
        body: JSON.stringify({ topic, body: JSON.stringify(msg) }),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }

  private parseDevice(device: any, location: any): WaterHeaterState | null {
    // Port of _parse_device from econet_client.py — same field extraction logic
    const serial = device.serial_number ?? device.serialNumber ?? '';
    if (!serial) return null;

    const val = (key: string, def: any = null) => {
      const raw = device[key];
      return raw && typeof raw === 'object' ? raw.value ?? def : raw ?? def;
    };

    const modeMap: Record<number, string> = {
      0: 'OFF', 1: 'ENERGY_SAVING', 2: 'HEAT_PUMP_ONLY',
      3: 'HIGH_DEMAND', 4: 'ELECTRIC_MODE', 5: 'VACATION',
    };

    const locAddr = location?.['@LOCATION_ADDRESS'] ?? {};

    return {
      deviceId: serial,
      deviceName: device.device_name ?? '',
      name: val('@NAME', serial)?.toString().trim() ?? serial,
      setpoint: parseFloat(val('@SETPOINT', 120)) || 120,
      setpointMin: 110,
      setpointMax: 140,
      currentTemp: null,
      hotWaterAvail: this.parseHotWaterImage(device['@HOTWATER']),
      mode: modeMap[parseInt(val('@MODE', 0)) || 0] ?? 'UNKNOWN',
      modes: Object.values(modeMap),
      running: Boolean(device['@RUNNING'] && String(device['@RUNNING']).trim()),
      runningState: device['@RUNNING'] ? String(device['@RUNNING']).trim() : null,
      wifiSignal: null,
      connected: Boolean(device['@CONNECTED']),
      active: Boolean(device['@ACTIVE'] ?? true),
      todaysEnergyKwh: null,
      compressorHealth: null,
      tankHealth: null,
      location: {
        city: locAddr.city ?? '',
        state: locAddr.state ?? '',
        zipcode: locAddr.zipcode ?? '',
      },
    };
  }

  private parseHotWaterImage(img: any): number | null {
    if (typeof img !== 'string') return null;
    const lower = img.toLowerCase();
    if (lower.includes('hundread_percent') || lower.includes('hundred_percent')) return 100;
    if (lower.includes('fourty_percent') || lower.includes('forty_percent')) return 66;
    if (lower.includes('ten_percent')) return 33;
    if (lower.includes('empty') || lower.includes('zero_percent')) return 0;
    return null;
  }
}
```

### EcoNet MQTT (Real-Time Updates)

The Python server uses `paho-mqtt` with raw TLS on port 1884. React Native cannot do raw TCP MQTT in managed Expo. Two options:

**Option A: ClearBlade WebSocket endpoint (preferred if available)**

ClearBlade typically exposes MQTT over WebSocket on port 8904 or 443. If `wss://rheem.clearblade.com:8904` is open, use `mqtt` (MQTT.js) directly:

```typescript
// src/services/econet-mqtt.ts
import mqtt from 'mqtt';

export function connectEcoNetMQTT(
  userToken: string,
  accountId: string,
  onStateUpdate: (deviceId: string, payload: any) => void,
): mqtt.MqttClient {
  const client = mqtt.connect('wss://rheem.clearblade.com:8904/mqtt', {
    username: userToken,
    password: CB_SYSTEM_KEY,
    clientId: `wattwise_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    protocolVersion: 4,
    clean: true,
  });

  client.on('connect', () => {
    client.subscribe(`user/${accountId}/device/reported`);
    client.subscribe(`user/${accountId}/device/desired`);
  });

  client.on('message', (topic, payload) => {
    try {
      const data = JSON.parse(payload.toString());
      const serial = data.serial_number ?? data.serialNumber ?? '';
      if (serial) onStateUpdate(serial, data);
    } catch { /* ignore parse errors */ }
  });

  return client;
}
```

**Option B: REST polling fallback**

If ClearBlade WebSocket is not available, fall back to polling `getEquipment()` every 30-60 seconds when the app is in the foreground. This is what the Python backend does with its `poller.py`.

```typescript
// Polling fallback — used if MQTT WebSocket is unavailable
export function startPolling(client: EcoNetClient, intervalMs = 30000): () => void {
  const timer = setInterval(async () => {
    await client.getEquipment();
  }, intervalMs);
  return () => clearInterval(timer);
}
```

**Recommendation:** Start with REST polling. Test the ClearBlade WebSocket endpoint. If it works, switch to MQTT. The polling approach is simpler and guaranteed to work.

### Kasa Local Control — Feasibility Analysis

Kasa smart plugs use a proprietary UDP/TCP protocol on the local network. React Native in Expo managed workflow **cannot** do raw UDP/TCP.

| Approach | Works in Expo Managed? | Notes |
|----------|------------------------|-------|
| Kasa Cloud API (HTTPS) | Yes | Requires TP-Link account, higher latency, depends on TP-Link servers |
| Local UDP discovery | No | Requires `react-native-udp` (native module) |
| Local TCP control | No | Requires `react-native-tcp-socket` (native module) |
| Expo bare workflow + native modules | Yes | Adds build complexity, requires prebuild |

**Recommendation for v1:** Use Kasa cloud API (HTTPS) for device monitoring (energy readings). If local control is critical, use Expo bare workflow from the start. For v1, Kasa devices are likely read-only (energy monitoring), so cloud API suffices.

### What Needs a Proxy/Edge Function

| API Call | Direct from App? | Proxy Needed? | Reason |
|----------|-----------------|---------------|--------|
| Supabase Auth | Yes | No | supabase-js handles everything |
| Supabase PostgREST | Yes | No | Row-level security handles auth |
| Supabase Realtime | Yes | No | Native WebSocket support |
| ClearBlade REST | Yes | No | Public system key, user token auth |
| ClearBlade MQTT (WebSocket) | Yes | No | If WSS endpoint exists |
| ClearBlade MQTT (raw TLS) | No | Edge function | Need Supabase Edge Function as MQTT proxy |
| Kasa Cloud API | Yes | No | Standard HTTPS |
| Kasa Local (UDP/TCP) | No | N/A | Native module or skip for v1 |

If raw MQTT is required and WebSocket is unavailable, create a Supabase Edge Function:

```typescript
// supabase/functions/mqtt-proxy/index.ts
// Receives REST commands from mobile, publishes to MQTT
// Returns device state from MQTT subscription
```

---

## 5. UI & Navigation

### Navigation Structure

Using Expo Router (file-based routing built on React Navigation):

```
Root (_layout.tsx) — Auth gate
├── (auth)/ — Login/Signup (no tab bar)
│   ├── login.tsx
│   ├── signup.tsx
│   └── forgot-password.tsx
│
└── (tabs)/ — Main app with bottom tab bar
    ├── index.tsx         — Dashboard (device status, quick controls)
    ├── devices/
    │   ├── index.tsx     — Device list (all locations)
    │   └── [id].tsx      — Device detail (full controls, live state)
    ├── optimize.tsx      — Schedule optimizer + active schedule view
    ├── history.tsx       — Energy charts, cost breakdown, export
    └── settings.tsx      — Account, TOU rates, preferences, EcoNet credentials
```

### Tab Bar Configuration

```typescript
// app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router';
import { Home, Cpu, Zap, BarChart3, Settings } from 'lucide-react-native';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#63b3ed',
        tabBarInactiveTintColor: '#8892a4',
        tabBarStyle: {
          backgroundColor: '#1a1d2e',
          borderTopColor: '#2d3148',
          height: 88,
          paddingBottom: 34, // Safe area on iPhone
        },
        headerStyle: { backgroundColor: '#1a1d2e' },
        headerTintColor: '#e2e8f0',
      }}
    >
      <Tabs.Screen name="index" options={{
        title: 'Dashboard',
        tabBarIcon: ({ color, size }) => <Home size={size} color={color} />,
      }} />
      <Tabs.Screen name="devices" options={{
        title: 'Devices',
        tabBarIcon: ({ color, size }) => <Cpu size={size} color={color} />,
      }} />
      <Tabs.Screen name="optimize" options={{
        title: 'Optimize',
        tabBarIcon: ({ color, size }) => <Zap size={size} color={color} />,
      }} />
      <Tabs.Screen name="history" options={{
        title: 'History',
        tabBarIcon: ({ color, size }) => <BarChart3 size={size} color={color} />,
      }} />
      <Tabs.Screen name="settings" options={{
        title: 'Settings',
        tabBarIcon: ({ color, size }) => <Settings size={size} color={color} />,
      }} />
    </Tabs>
  );
}
```

### Charts Library

**Victory Native + Skia** is the recommended combination:

- `victory-native@41+` uses `@shopify/react-native-skia` for GPU-accelerated rendering
- Smooth 60fps animations on both platforms
- Supports bar charts (hourly energy), line charts (daily trends), pie charts (TOU breakdown)
- Expo-compatible (Skia ships as a prebuilt binary, no native build step)

Alternative: `react-native-chart-kit` is simpler but less performant and visually limited. For the energy dashboard with interactive charts, Victory Native is worth the dependency.

```typescript
// src/components/charts/EnergyBarChart.tsx
import { CartesianChart, Bar, useChartPressState } from 'victory-native';
import { useFont } from '@shopify/react-native-skia';

interface Props {
  data: { hour: number; kwh: number; touTier: string }[];
}

export function EnergyBarChart({ data }: Props) {
  const font = useFont(require('../../../assets/fonts/Inter-Regular.otf'), 12);
  const { state, isActive } = useChartPressState({ x: 0, y: { kwh: 0 } });

  const tierColors: Record<string, string> = {
    peak: '#fc8181',
    mid_peak: '#f6ad55',
    off_peak: '#68d391',
  };

  return (
    <CartesianChart
      data={data}
      xKey="hour"
      yKeys={['kwh']}
      axisOptions={{ font, lineColor: '#2d3148', labelColor: '#8892a4' }}
      chartPressState={state}
    >
      {({ points, chartBounds }) => (
        <Bar
          points={points.kwh}
          chartBounds={chartBounds}
          color={({ datum }) => tierColors[datum.touTier] ?? '#63b3ed'}
          roundedCorners={{ topLeft: 4, topRight: 4 }}
          animate={{ type: 'spring' }}
        />
      )}
    </CartesianChart>
  );
}
```

### Design System

Port the existing CSS custom properties to a React Native theme object. The existing web app supports light/dark themes — carry that forward.

```typescript
// src/theme/colors.ts
export const colors = {
  light: {
    bg: '#f4f6f8',
    surface: '#ffffff',
    surfaceAlt: '#f7fafc',
    border: '#e2e6ea',
    text: '#1a202c',
    textMuted: '#718096',
    accent: '#2b6cb0',
    accentLight: '#ebf4ff',
    danger: '#e53e3e',
    warn: '#dd6b20',
    success: '#38a169',
    touPeak: '#e53e3e',
    touMid: '#dd6b20',
    touOff: '#38a169',
  },
  dark: {
    bg: '#0f1117',
    surface: '#1a1d2e',
    surfaceAlt: '#232638',
    border: '#2d3148',
    text: '#e2e8f0',
    textMuted: '#8892a4',
    accent: '#63b3ed',
    accentLight: '#1a2744',
    danger: '#fc8181',
    warn: '#f6ad55',
    success: '#68d391',
    touPeak: '#fc8181',
    touMid: '#f6ad55',
    touOff: '#68d391',
  },
} as const;

// src/theme/spacing.ts
export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  full: 9999,
} as const;
```

### Key Screen Wireframes

**Dashboard (index.tsx)**
- Device status card: name, setpoint, mode, hot water level (gauge), running indicator
- Quick temperature slider (+/- buttons)
- Mode selector (horizontal scroll of mode pills)
- Today's energy summary (kWh, cost, TOU breakdown mini bar)
- Connection status badge (MQTT/polling, last updated timestamp)

**Device Detail ([id].tsx)**
- Full temperature control (large circular dial or slider, min/max bounds)
- Mode grid (all 6 modes with icons)
- Live state: running state text, hot water gauge, compressor/tank health bars
- Location badge
- Today's hourly energy bar chart (inline)

**History (history.tsx)**
- Period selector: Day | Week | Month | Quarter | Year (horizontal pill row)
- Main chart: hourly bars (day view) or daily bars (week+ view), colored by TOU tier
- Summary cards: total kWh, total cost, peak/mid/off breakdown
- Export button (share CSV via `expo-sharing`)

**Optimize (optimize.tsx)**
- Current schedule timeline (visual blocks per day)
- "Optimize" button runs the optimizer logic (ported from `optimizer.py`)
- Before/after cost comparison
- Apply / revert controls
- Copy schedule day-to-day

**Settings (settings.tsx)**
- Account section: email, sign out
- EcoNet credentials: email/password (stored in SecureStore)
- TOU rate editor: list of tiers with start/end hour, rate, days
- Comfort preferences: min temp, max recovery, preferred setpoint, away setpoint
- Sync status: last sync time, manual sync button
- Theme toggle (light/dark)
- App version, diagnostics

---

## 6. Build & Deploy

### EAS Build Configuration

```json
// eas.json
{
  "cli": { "version": ">= 13.0.0" },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": { "simulator": true },
      "env": {
        "EXPO_PUBLIC_SUPABASE_URL": "https://your-project.supabase.co",
        "EXPO_PUBLIC_SUPABASE_ANON_KEY": "your-anon-key"
      }
    },
    "preview": {
      "distribution": "internal",
      "ios": { "enterpriseProvisioning": "universal" },
      "env": {
        "EXPO_PUBLIC_SUPABASE_URL": "https://your-project.supabase.co",
        "EXPO_PUBLIC_SUPABASE_ANON_KEY": "your-anon-key"
      }
    },
    "production": {
      "autoIncrement": true,
      "env": {
        "EXPO_PUBLIC_SUPABASE_URL": "https://your-project.supabase.co",
        "EXPO_PUBLIC_SUPABASE_ANON_KEY": "your-anon-key"
      }
    }
  },
  "submit": {
    "production": {
      "ios": {
        "appleId": "your-apple-id@example.com",
        "ascAppId": "your-app-store-connect-app-id",
        "appleTeamId": "YOUR_TEAM_ID"
      },
      "android": {
        "serviceAccountKeyPath": "./google-services.json",
        "track": "internal"
      }
    }
  }
}
```

### Environment Configuration

```json
// app.json
{
  "expo": {
    "name": "WattWise",
    "slug": "wattwise",
    "version": "1.0.0",
    "scheme": "wattwise",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "splash": {
      "image": "./assets/splash.png",
      "resizeMode": "contain",
      "backgroundColor": "#0f1117"
    },
    "ios": {
      "bundleIdentifier": "com.wattwise.app",
      "supportsTablet": true,
      "infoPlist": {
        "NSLocalNetworkUsageDescription": "WattWise discovers smart devices on your local network."
      }
    },
    "android": {
      "package": "com.wattwise.app",
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#0f1117"
      }
    },
    "plugins": [
      "expo-router",
      "expo-secure-store",
      "expo-sqlite"
    ],
    "updates": {
      "url": "https://u.expo.dev/your-project-id"
    },
    "runtimeVersion": {
      "policy": "appVersion"
    }
  }
}
```

### Build & Distribution Commands

```bash
# Install EAS CLI
npm install -g eas-cli

# Configure project
eas build:configure

# Development build (with dev client for debugging)
eas build --profile development --platform ios
eas build --profile development --platform android

# Preview build (internal distribution — TestFlight / internal track)
eas build --profile preview --platform ios
eas build --profile preview --platform android

# Production build
eas build --profile production --platform all

# Submit to stores
eas submit --platform ios    # Uploads to TestFlight / App Store Connect
eas submit --platform android  # Uploads to Google Play Console

# Over-the-air update (JS-only changes, no native module changes)
eas update --branch production --message "Fix energy chart rendering"
```

### TestFlight Distribution

1. Run `eas build --profile preview --platform ios`
2. Run `eas submit --platform ios` (uploads .ipa to App Store Connect)
3. In App Store Connect, add internal testers to the TestFlight group
4. Testers receive TestFlight notification on their iOS devices

### App Store Considerations

- **Privacy nutrition labels:** WattWise collects email (account), energy usage data (app functionality), device identifiers (analytics). Declare these in App Store Connect.
- **Background modes:** Not needed for v1 (no background fetch or location). If background energy polling is added later, declare `fetch` capability.
- **Local network permission (iOS 14+):** Required if Kasa local control is added. Add `NSLocalNetworkUsageDescription` to Info.plist.
- **In-app purchases:** Not needed unless premium features are gated (future consideration).
- **Review guidelines:** Energy monitoring apps are straightforward. Device control apps may get extra scrutiny — ensure safety bounds (110-140F) are enforced client-side AND in the ClearBlade API call.

---

## 7. Migration Path

### What Can Be Reused From the Web Frontend

| Component | Reuse Level | Notes |
|-----------|-------------|-------|
| Auth logic (Supabase JS) | High | Same `@supabase/supabase-js` calls, different storage adapter |
| EcoNet API calls | High | Port `econet_client.py` to TypeScript (REST calls are identical) |
| Supabase sync logic | High | Port `supabase_sync.py` to TypeScript (PostgREST calls) |
| Data models / schemas | High | Port `schemas.py` Pydantic models to TypeScript interfaces |
| TOU rate calculation | Medium | Port `optimizer.py` logic, simplify for mobile |
| HTML templates | None | Complete rewrite as React Native components |
| CSS styles | Low | Theme colors/values carry over; layout is completely different |
| MQTT client | Low | Different library (MQTT.js vs paho-mqtt), same topic structure |

### What Must Be Rewritten

1. **All UI** — Jinja2 HTML templates become React Native screens/components
2. **Navigation** — Server-side routing becomes Expo Router
3. **State management** — Server-side SQLAlchemy ORM becomes Zustand + expo-sqlite
4. **Background polling** — FastAPI `apscheduler` becomes foreground-only polling with AppState hooks
5. **MQTT** — `paho-mqtt` (Python, raw TLS) becomes MQTT.js (WebSocket) or REST polling

### Recommended Implementation Order

#### Phase 1: Foundation (Weeks 1-2)

1. **Project scaffolding** — Expo init, directory structure, dependencies
2. **Supabase auth** — Login, signup, magic link, session persistence, auth gate
3. **Theme system** — Colors, spacing, dark mode, base components (Card, Button, Input)
4. **Navigation shell** — Tab bar with placeholder screens
5. **Local database** — expo-sqlite schema, migration runner, basic CRUD

#### Phase 2: Core Features (Weeks 3-4)

6. **EcoNet client (TypeScript)** — Login, getEquipment, device parsing
7. **Dashboard screen** — Device status card, temperature display, mode badge
8. **Device control** — Setpoint slider, mode selector (via ClearBlade REST messaging API)
9. **EcoNet credential storage** — SecureStore integration, settings screen input
10. **REST polling** — Foreground polling loop, AppState management

#### Phase 3: Data & Charts (Weeks 5-6)

11. **Energy data fetching** — Port getEnergyUsage, store in SQLite
12. **History screen** — Period selector, Victory Native bar chart (TOU-colored)
13. **TOU rates** — Local storage, Supabase pull, cost calculation
14. **Daily summary aggregation** — Compute from hourly data, store locally
15. **Data export** — CSV generation, share via expo-sharing

#### Phase 4: Optimization & Sync (Weeks 7-8)

16. **Schedule management** — View, edit, copy schedule entries
17. **Optimizer** — Port optimizer.py logic for schedule suggestions
18. **Supabase sync engine** — Push readings, pull config, bidirectional schedules
19. **Network-aware sync** — Auto-sync on foreground, on network restore
20. **Conflict resolution** — Last-write-wins for schedules, append-only for readings

#### Phase 5: Polish & Ship (Weeks 9-10)

21. **MQTT real-time** — Test ClearBlade WebSocket, implement if available
22. **Push notifications** — expo-notifications for alerts (device offline, high usage)
23. **Multi-device support** — Location grouping, device switcher
24. **Error handling** — Retry logic, offline indicators, toast messages
25. **Testing** — Unit tests (stores, API clients), integration tests (auth flow)
26. **EAS Build** — Development, preview, production profiles
27. **TestFlight beta** — Internal testing, bug fixes
28. **App Store submission**

### File-by-File Migration Map

```
Python Source                    →  TypeScript Target
─────────────────────────────────────────────────────
src/backend/econet_client.py     →  src/services/econet.ts
src/backend/supabase_sync.py     →  src/db/sync.ts
src/backend/models.py            →  src/db/schema.ts (SQL) + types in each store
src/backend/schemas.py           →  TypeScript interfaces in stores and services
src/backend/auth.py              →  src/stores/auth.ts (Supabase JS handles JWT)
src/backend/config.py            →  Environment variables (EXPO_PUBLIC_*)
src/backend/optimizer.py         →  src/services/optimizer.ts
src/backend/routes_api.py        →  Logic distributed across stores (no server)
src/backend/poller.py            →  Foreground polling in device store
src/frontend/templates/*.html    →  app/(tabs)/*.tsx screens
src/frontend/static/css/style.css → src/theme/colors.ts, spacing.ts
```

---

## Appendix A: Key Technical Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Expo SDK 52 (managed) | No native modules needed for v1; EAS Build; OTA updates |
| Routing | Expo Router v4 | File-based, built on React Navigation, deep linking support |
| State | Zustand 5 | Minimal boilerplate, no providers, easy persistence |
| Local DB | expo-sqlite | Built into Expo, synchronous API, sufficient for data volume |
| KV Store | react-native-mmkv | Fastest KV store for RN, sync timestamps and preferences |
| Auth | @supabase/supabase-js | Same SDK as web, SecureStore adapter for token persistence |
| Token storage | expo-secure-store | iOS Keychain / Android Keystore backed |
| Charts | Victory Native + Skia | GPU-accelerated, interactive, good bar chart support |
| MQTT | REST polling (v1), MQTT.js WebSocket (v2) | Polling is reliable; MQTT WebSocket needs ClearBlade endpoint testing |
| Sync | Push-primary, pull-secondary | App owns readings; Supabase owns config |
| Icons | lucide-react-native | Consistent, tree-shakeable, matches web iconography |
| Build | EAS Build | Cloud builds, no local Xcode/AS dependency |

## Appendix B: Dependency Version Matrix

| Package | Version | Expo SDK 52 Compatible |
|---------|---------|----------------------|
| expo | ~52.0.0 | Yes (baseline) |
| react-native | 0.76.x | Yes (bundled) |
| @supabase/supabase-js | ^2.45.0 | Yes |
| expo-sqlite | ~15.0.0 | Yes (new sync API) |
| expo-secure-store | ~14.0.0 | Yes |
| expo-router | ~4.0.0 | Yes |
| zustand | ^5.0.0 | Yes |
| victory-native | ^41.0.0 | Yes (requires Skia) |
| @shopify/react-native-skia | ^1.5.0 | Yes |
| mqtt (MQTT.js) | ^5.10.0 | Yes (WebSocket only) |
| react-native-mmkv | ^3.2.0 | Yes |
| react-native-reanimated | ~3.16.0 | Yes (bundled with Expo) |
| date-fns | ^4.1.0 | Yes (pure JS) |
| lucide-react-native | ^0.475.0 | Yes |
| @react-native-community/netinfo | ^11.4.0 | Yes |
