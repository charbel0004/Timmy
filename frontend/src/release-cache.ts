/** A unique document URL bypasses stale HTML without clearing login cookies. */
export function freshApplicationUrl(href: string, timestamp = Date.now()) {
  const url = new URL(href);
  url.pathname = '/';
  url.searchParams.set('_timmy_refresh', String(timestamp));
  return url.toString();
}
