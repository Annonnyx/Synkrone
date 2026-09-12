'use strict';

const { panelAdmin } = require('./admin-ops');
const { peekWallet, spendFromLedger } = require('./krones');
const { discordUserId, OFFICIAL_BOTS } = require('./serveur');

const DISCORD_API = 'https://discord.com/api/v10';

function oauthProviders() {
    return {
        discord: Boolean(
            String(process.env.DISCORD_CLIENT_ID || '').trim()
            && String(process.env.DISCORD_CLIENT_SECRET || '').trim()
            && String(process.env.DISCORD_REDIRECT_URI || '').trim()
        ),
        github: Boolean(
            String(process.env.GITHUB_CLIENT_ID || '').trim()
            && String(process.env.GITHUB_CLIENT_SECRET || '').trim()
        ),
        google: Boolean(
            String(process.env.GOOGLE_CLIENT_ID || '').trim()
            && String(process.env.GOOGLE_CLIENT_SECRET || '').trim()
        )
    };
}

function supportGuildId() {
    return String(process.env.DISCORD_SUPPORT_GUILD_ID || process.env.DISCORD_GUILD_ID || '').trim();
}

async function supportRoles(discordId) {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    const guildId = supportGuildId();
    if (!token || !guildId || !discordId) {
        return { configured: false, roles: [] };
    }
    try {
        const [memberRes, rolesRes] = await Promise.all([
            fetch(`${DISCORD_API}/guilds/${guildId}/members/${discordId}`, {
                headers: { Authorization: `Bot ${token}` },
                signal: AbortSignal.timeout(2500)
            }),
            fetch(`${DISCORD_API}/guilds/${guildId}/roles`, {
                headers: { Authorization: `Bot ${token}` },
                signal: AbortSignal.timeout(2500)
            })
        ]);
        if (!memberRes.ok) return { configured: true, member: false, roles: [] };
        const member = await memberRes.json();
        const allRoles = rolesRes.ok ? await rolesRes.json() : [];
        const mine = new Set(member.roles || []);
        const roles = (Array.isArray(allRoles) ? allRoles : [])
            .filter((role) => mine.has(role.id) && role.name !== '@everyone')
            .sort((a, b) => (b.position || 0) - (a.position || 0))
            .map((role) => ({ id: role.id, name: role.name }));
        return { configured: true, member: true, roles };
    } catch {
        return { configured: true, member: false, roles: [] };
    }
}

function mountCompte(app) {
    app.get('/api/compte', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) {
            return res.status(401).json({
                ok: false,
                loginUrl: '/login?returnTo=/compte'
            });
        }
        const discordId = discordUserId(user);
        const email = String(user.email || '').trim().toLowerCase();
        const providers = user.providers && typeof user.providers === 'object' ? { ...user.providers } : {};
        if (discordId) providers.discord = discordId;
        const prefixed = String(user.id || '').match(/^(github|google):(.+)$/);
        if (prefixed && !providers[prefixed[1]]) providers[prefixed[1]] = prefixed[2];
        const wallet = await peekWallet(user.id).catch(() => null);
        const spend = spendFromLedger(wallet?.ledger || []);
        let services = [];
        let linkedPanel = false;
        let servicesError = null;
        const query = new URLSearchParams();
        if (discordId) query.set('discordUserId', discordId);
        if (email) query.set('email', email);
        if (discordId || email) {
            try {
                const data = await panelAdmin(`/discord?${query.toString()}`);
                linkedPanel = Boolean(data.linked);
                services = Array.isArray(data.services) ? data.services : [];
            } catch (err) {
                services = [];
                servicesError = err instanceof Error ? err.message : 'Panel injoignable.';
                console.warn('[compte] services panel:', servicesError);
            }
        }
        const guilds = [];
        const seen = new Set();
        for (const svc of services) {
            for (const g of svc.guilds || []) {
                const key = `${g.id}:${svc.applicationId || svc.id}`;
                if (seen.has(key)) continue;
                seen.add(key);
                guilds.push({
                    id: g.id,
                    name: g.name,
                    bot: svc.name,
                    applicationId: svc.applicationId,
                    href: svc.applicationId ? `/serveur?guild=${g.id}&application=${svc.applicationId}` : '/serveur'
                });
            }
        }
        const roles = discordId
            ? await supportRoles(discordId)
            : { configured: false, roles: [], discordOnly: true };
        return res.json({
            ok: true,
            user: {
                id: user.id,
                username: user.username,
                avatar: user.avatar,
                role: user.role,
                discordId,
                email
            },
            connections: {
                discord: Boolean(discordId),
                github: Boolean(providers.github),
                google: Boolean(providers.google)
            },
            oauth: oauthProviders(),
            support: roles,
            krones: {
                balance: wallet?.balance ?? 0,
                plan: wallet?.plan || 'Aucun',
                spentTotal: spend.total,
                spentMonth: spend.month
            },
            services: services.map((svc) => ({
                id: svc.id,
                name: svc.name,
                type: svc.type,
                state: svc.state,
                flavor: svc.flavor
            })),
            linkedPanel,
            servicesError,
            guilds,
            officialBots: OFFICIAL_BOTS.map((b) => ({ slug: b.slug, name: b.name, applicationId: b.applicationId })),
            panelUrl: '/hebergement'
        });
    });
}

module.exports = { mountCompte, supportRoles };
