import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { api } from "@/lib/api";

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },
  providers: [
    CredentialsProvider({
      name: "Admin",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(creds) {
        if (!creds?.email || !creds.password) return null;
        try {
          const profile = await api.login(creds.email, creds.password);
          return {
            id: profile.id,
            email: profile.email,
            // NextAuth User type requires `name`; we use email as a friendly label
            // and stash `role` on the user object for the jwt callback to pick up.
            name: profile.email,
            role: profile.role,
          } as any;
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        const u = user as any;
        token.uid = u.id;
        token.role = u.role;
        token.email = u.email;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as any).id = token.uid;
        (session.user as any).role = token.role;
      }
      return session;
    },
  },
  pages: { signIn: "/login" },
};
