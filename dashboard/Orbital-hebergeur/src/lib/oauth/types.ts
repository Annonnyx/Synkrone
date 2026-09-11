export const OAUTH_PROVIDERS = ["github", "google", "discord"] as const;
export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];
export type OAuthIntent = "login" | "link";

export type OAuthProfile = {
  id: string;
  email: string | null;
  emailVerified: boolean;
  name: string;
  avatarUrl: string | null;
  login: string | null;
};

export type OAuthTokens = {
  accessToken: string;
  refreshToken?: string | null;
  expiresIn?: number | null;
  scope?: string | null;
};

export type GithubRepo = {
  fullName: string;
  htmlUrl: string;
  cloneUrl: string;
  defaultBranch: string;
  private: boolean;
  description: string | null;
};

export type ProviderStatus = {
  id: OAuthProvider;
  configured: boolean;
  linked: boolean;
  login: string | null;
  email: string | null;
};

export function isOAuthProvider(value: string): value is OAuthProvider {
  return (OAUTH_PROVIDERS as readonly string[]).includes(value);
}
