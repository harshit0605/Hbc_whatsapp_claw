import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Society Admin",
  description: "Society maintenance ticketing & dispatch",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions);
  return (
    <html lang="en">
      <body className="min-h-screen">
        {session ? <Nav /> : null}
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}

function Nav() {
  return (
    <nav className="border-b border-line bg-panel">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
        <Link href="/" className="font-semibold text-ink">
          🏢 Society Admin
        </Link>
        <Link href="/queue" className="text-sm text-muted hover:text-ink">Queue</Link>
        <Link href="/residents" className="text-sm text-muted hover:text-ink">Residents</Link>
        <Link href="/workers" className="text-sm text-muted hover:text-ink">Workers</Link>
        <Link href="/analytics" className="text-sm text-muted hover:text-ink">Analytics</Link>
        <Link href="/settings" className="text-sm text-muted hover:text-ink">Settings</Link>
        <div className="ml-auto">
          <Link href="/api/auth/signout" className="text-sm text-muted hover:text-ink">
            Sign out
          </Link>
        </div>
      </div>
    </nav>
  );
}
