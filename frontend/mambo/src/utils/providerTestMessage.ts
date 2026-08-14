import i18n from '@/i18n';

const PROVIDER_TEST_CODE_KEYS: Record<string, string> = {
  CONNECTION_OK: 'provider.test.success',
  CONNECTION_INVALID_JSON: 'provider.test.invalidJson',
  CONNECTION_HTTP_ERROR: 'provider.test.httpError',
  CONNECTION_PROXY_ERROR: 'provider.test.proxyError',
  CONNECTION_REQUEST_ERROR: 'provider.test.requestError',
  CONNECTION_UNKNOWN: 'provider.test.unknown',
};

export function localizeProviderTestMessage(code?: string | null): string | null {
  if (!code) return null;
  const key = PROVIDER_TEST_CODE_KEYS[code];
  if (!key) return null;
  return i18n.global.t(key);
}
