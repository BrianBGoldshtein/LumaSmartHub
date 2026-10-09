// Dormant 0.3.0 protocol helpers. No networking, UI registration or enrollment
// happens on import. A browser key is not physical-phone attestation.
export type BrowserKey = {privateKey: CryptoKey; publicKey: string};
export type RemoteContext = {origin: string; identityDigest: string};

const token = /^[A-Za-z0-9_-]{43}$/;
const digest = /^[0-9a-f]{64}$/;
const privateOrigin = /^https:\/\/[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z0-9-]{1,63}\.ts\.net$/;
const operations = new Set([
  'GET /remote/api/admin/status', 'POST /remote/api/admin/unlock', 'POST /remote/api/admin/lock',
  'GET /remote/api/personal-settings', 'PATCH /remote/api/personal-settings',
  'GET /remote/api/setup', 'POST /remote/api/setup',
  'GET /remote/api/preview', 'GET /remote/api/settings', 'PATCH /remote/api/settings',
  'POST /remote/api/command', 'GET /remote/api/google/status', 'GET /remote/api/google/calendars',
  'GET /remote/api/google/colors', 'POST /remote/api/google/sync', 'POST /remote/api/google/web-client',
  'POST /remote/api/google/authorize', 'POST /remote/api/todos/complete',
  'GET /remote/api/updates/status', 'POST /remote/api/updates/check', 'POST /remote/api/updates/install',
]);
const encoder = new TextEncoder();
const validToken = (value:string) => value.length === 43 && token.test(value);

export function encodeProof(raw: Uint8Array): string {
  return btoa(Array.from(raw, byte => String.fromCharCode(byte)).join(''))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function point(value: string): Uint8Array {
  if (value.length !== 87 || !/^[A-Za-z0-9_-]{87}$/.test(value)) throw new Error('Invalid browser public key.');
  const raw = Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='), c => c.charCodeAt(0));
  if (raw.length !== 65 || raw[0] !== 4 || encodeProof(raw) !== value) throw new Error('Invalid browser public key.');
  return raw;
}

function context(value: RemoteContext) {
  if (!privateOrigin.test(value.origin) || value.origin.trim() !== value.origin
    || value.origin.length > 200 || !digest.test(value.identityDigest) || value.identityDigest.length !== 64) {
    throw new Error('A private Luma connection is required.');
  }
}

export async function sha256(bytes: Uint8Array): Promise<string> {
  // Copy to a normal ArrayBuffer, not a caller-controlled shared buffer.
  const result = new Uint8Array(await crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer));
  return Array.from(result, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function createBrowserKey(): Promise<BrowserKey> {
  if (globalThis.isSecureContext === false || !globalThis.crypto?.subtle) throw new Error('Use Luma’s private HTTPS address.');
  const pair = await crypto.subtle.generateKey({name: 'ECDSA', namedCurve: 'P-256'}, false, ['sign', 'verify']);
  const publicKey = encodeProof(new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey)));
  return {privateKey: pair.privateKey, publicKey};
}

export async function enrollmentBytes(ticket: string, connection: RemoteContext, publicKey: string): Promise<Uint8Array> {
  context(connection);
  if (!validToken(ticket)) throw new Error('Enrollment expired. Request a new QR on Luma.');
  return encoder.encode(['LUMA_ENROLL_V1', ticket, connection.origin, connection.identityDigest,
    await sha256(point(publicKey))].join('\n'));
}

export async function requestBytes(deviceId: string, nonce: string, connection: RemoteContext,
  method: string, path: string, body: Uint8Array): Promise<Uint8Array> {
  context(connection);
  if (!validToken(deviceId) || !validToken(nonce) || !operations.has(`${method} ${path}`)
    || body.length > 65536 || (method === 'GET' && body.length !== 0)) throw new Error('Invalid remote request.');
  return encoder.encode(['LUMA_REMOTE_V1', connection.origin, connection.identityDigest, deviceId, nonce,
    method, path, await sha256(body)].join('\n'));
}

export async function signProof(key: BrowserKey, message: Uint8Array): Promise<string> {
  if (key.privateKey.type !== 'private' || key.privateKey.extractable || key.privateKey.algorithm.name !== 'ECDSA'
    || (key.privateKey.algorithm as EcKeyAlgorithm).namedCurve !== 'P-256') throw new Error('Re-enroll this browser on Luma.');
  return encodeProof(new Uint8Array(await crypto.subtle.sign({name: 'ECDSA', hash: 'SHA-256'},
    key.privateKey, new Uint8Array(message).buffer)));
}

// Only a CryptoKey/public point/browser ID is persisted here. Never store hub
// state, account secrets, private preview data, PIN, ticket or challenge nonce.
export type BrowserCredential = BrowserKey & {deviceId: string};
export async function credentialStore(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('luma-remote-key-v1', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('credentials');
    request.onerror = () => reject(new Error('Browser storage is unavailable. Enrollment was not saved.'));
    request.onblocked = () => reject(new Error('Close other Luma windows and try again.'));
    request.onsuccess = () => resolve(request.result);
  });
}

export async function saveCredential(value: BrowserCredential): Promise<void> {
  if (!validToken(value.deviceId)) throw new Error('Invalid enrollment.');
  point(value.publicKey);
  // Test the private-key shape without exporting or persisting private bytes.
  await signProof(value, encoder.encode('LUMA_STORAGE_CHECK_V1'));
  const db = await credentialStore();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction('credentials', 'readwrite');
      transaction.objectStore('credentials').put({privateKey:value.privateKey,
        publicKey:value.publicKey,deviceId:value.deviceId}, 'selected');
      transaction.oncomplete = () => resolve();
      transaction.onerror = transaction.onabort = () => reject(new Error('Enrollment was not saved. Try again.'));
    });
  } finally { db.close(); }
}

export async function loadCredential(): Promise<BrowserCredential | null> {
  const db = await credentialStore();
  try {
    const value = await new Promise<BrowserCredential | undefined>((resolve, reject) => {
      const transaction = db.transaction('credentials', 'readonly');
      const request = transaction.objectStore('credentials').get('selected');
      let result: BrowserCredential | undefined;
      request.onsuccess = () => { result = request.result; };
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = transaction.onabort = () => reject(new Error('Browser key is unavailable. Re-enroll on Luma.'));
    });
    if (!value) return null;
    if (!validToken(value.deviceId)) throw new Error('Browser key is invalid. Re-enroll on Luma.');
    point(value.publicKey);
    await signProof(value, encoder.encode('LUMA_STORAGE_CHECK_V1'));
    return value;
  } finally { db.close(); }
}
