import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly";
const GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          scope: `openid email profile ${GA4_SCOPE} ${GSC_SCOPE}`,
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        token.googleAccessToken = account.access_token;
        token.googleRefreshToken = account.refresh_token;
        token.googleIdToken = account.id_token;
        token.googleSub = account.providerAccountId;
      }
      return token;
    },
    async session({ session, token }) {
      session.googleAccessToken = token.googleAccessToken as string | undefined;
      session.googleRefreshToken = token.googleRefreshToken as string | undefined;
      session.googleIdToken = token.googleIdToken as string | undefined;
      session.googleSub = token.googleSub as string | undefined;
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
});
