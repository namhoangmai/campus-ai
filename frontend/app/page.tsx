/**
 * Root page. v1's root page was the entire TU/e chat UI; in v2 the chat UI moved to
 * app/widget/page.tsx (loaded inside a tenant's embedded iframe, keyed by widget key -- see
 * ARCHITECTURE.md §8), because "/" has no tenant context to answer questions for. This page is
 * now just an operator-facing landing note. A self-serve marketing site is explicitly out of
 * scope for this phase (ARCHITECTURE.md §12) -- this is a placeholder, not a product surface.
 */
export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-4 py-8 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Campus-AI</h1>
      <p className="text-sm text-neutral-500">
        This app serves the embeddable chat widget for onboarded university tenants at{" "}
        <code className="rounded bg-neutral-100 px-1.5 py-0.5">/widget?key=&lt;widget_key&gt;</code>.
        Tenants are provisioned via the admin CLI -- see the repo&apos;s README and{" "}
        <code className="rounded bg-neutral-100 px-1.5 py-0.5">ARCHITECTURE.md</code>.
      </p>
    </div>
  );
}
