import { route } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { publicBaseDomain } from "@/lib/domains/public";
import { listProviderStatus } from "@/lib/oauth/accounts";
import { oauthRedirectUri, publicOrigin } from "@/lib/oauth/providers";
import { originFromRequest } from "@/lib/oauth/public-origin";
import { OAUTH_PROVIDERS } from "@/lib/oauth/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  return route(async () => {
    const user = await getCurrentUser();
    const origin = publicOrigin(originFromRequest(req));
    const base = publicBaseDomain();
    return {
      providers: await listProviderStatus(user?.id),
      redirectUris: Object.fromEntries(
        OAUTH_PROVIDERS.map((id) => [id, oauthRedirectUri(id, origin)]),
      ),
      publicBaseDomain: base.domain,
      domainPendingPurchase: !base.configured,
    };
  });
}
