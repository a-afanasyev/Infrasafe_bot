// Open-redirect guard for the ?next= return-to param used by the login flow:
// only allow same-origin absolute paths. Reject protocol-relative (`//evil.com`)
// and absolute URLs (`https://evil.com`) so a crafted /login?next=... link can't
// bounce the user off-site after authenticating.
export function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/dashboard'
  return raw
}
