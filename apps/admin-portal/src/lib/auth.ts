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
          return { id: profile.id, email: profile.email, name: profile.role };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.role = (user as any).name;
      }
      return token;
    },
    async session({ session, token }) {
      if (token.role) (session.user as any).role = token.role;
      return session;
    },
  },
  pages: { signIn: "/login" },
};
