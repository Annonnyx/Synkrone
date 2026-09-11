(function initContactForm() {
    const form = document.getElementById('contact-form');
    const statusEl = document.getElementById('contact-status');
    const discordLinkEls = Array.from(document.querySelectorAll('[data-discord-link]'));
    const loadingCard = document.getElementById('contact-loading');
    const loginCard = document.getElementById('contact-login-card');
    const loginTextEl = document.getElementById('contact-login-text');
    const joinCard = document.getElementById('contact-join-card');
    const joinTextEl = document.getElementById('contact-join-text');
    const ticketWrap = document.getElementById('contact-ticket-wrap');
    const guildNameEl = document.getElementById('contact-guild-name');
    const guildIconEl = document.getElementById('contact-guild-icon');
    const submitBtn = document.getElementById('contact-submit');

    if (!form || !statusEl) {
        return;
    }

    let canSubmitTicket = false;

    function showState(state) {
        if (loadingCard) loadingCard.classList.add('hidden');
        if (loginCard) loginCard.classList.add('hidden');
        if (joinCard) joinCard.classList.add('hidden');
        if (ticketWrap) ticketWrap.classList.add('hidden');

        if (state === 'loading' && loadingCard) loadingCard.classList.remove('hidden');
        if (state === 'login' && loginCard) loginCard.classList.remove('hidden');
        if (state === 'join' && joinCard) joinCard.classList.remove('hidden');
        if (state === 'ticket' && ticketWrap) ticketWrap.classList.remove('hidden');
    }

    function applyInviteUrl(inviteUrl) {
        if (typeof inviteUrl !== 'string' || !inviteUrl.trim()) return;
        discordLinkEls.forEach((linkEl) => {
            linkEl.href = inviteUrl.trim();
        });
    }

    function renderGuild(guild) {
        if (!guild) return;
        if (guildNameEl && typeof guild.name === 'string' && guild.name.trim()) {
            guildNameEl.textContent = guild.name.trim();
        }
        if (guildIconEl && typeof guild.iconUrl === 'string' && guild.iconUrl.trim()) {
            guildIconEl.src = guild.iconUrl.trim();
        }
    }

    function setSubmitAvailability(allowed, cooldownSecondsRemaining = 0) {
        canSubmitTicket = allowed;
        if (!submitBtn) return;

        const cooldown = Number(cooldownSecondsRemaining || 0);
        if (!allowed) {
            submitBtn.disabled = true;
            submitBtn.textContent = cooldown > 0
                ? `Patientez ${Math.ceil(cooldown / 60)} min`
                : 'Envoyer au support';
            return;
        }

        submitBtn.disabled = cooldown > 0;
        submitBtn.textContent = cooldown > 0
            ? `Patientez ${Math.ceil(cooldown / 60)} min`
            : 'Envoyer au support';
    }

    function showLoginMessage(message) {
        if (loginTextEl) {
            loginTextEl.textContent = message;
        }
        setSubmitAvailability(false);
        showState('login');
    }

    function showJoinMessage(message) {
        if (joinTextEl) {
            joinTextEl.textContent = message;
        }
        setSubmitAvailability(false);
        showState('join');
    }

    function showTicketState(cooldownSecondsRemaining) {
        const cooldown = Number(cooldownSecondsRemaining || 0);
        setSubmitAvailability(true, cooldown);
        if (cooldown > 0) {
            setStatus(`Vous pourrez renvoyer une demande dans ${Math.ceil(cooldown / 60)} minute(s).`, 'error');
        }
        showState('ticket');
    }

    async function applyContactConfig() {
        try {
            const response = await fetch('/api/contact-config');
            const data = await response.json();
            if (response.ok && data?.ok && typeof data.inviteUrl === 'string' && data.inviteUrl.trim()) {
                discordLinkEls.forEach((linkEl) => {
                    linkEl.href = data.inviteUrl.trim();
                });
            }
        } catch (error) {
            // On garde le lien par défaut défini dans le HTML.
            console.warn('Configuration contact indisponible:', error);
        }
    }

    async function applyContactState() {
        showState('loading');
        setSubmitAvailability(false);

        try {
            const response = await fetch('/api/contact-state');
            const data = await response.json().catch(() => ({}));
            applyInviteUrl(data?.inviteUrl);
            renderGuild(data?.guild);

            if (!response.ok || !data?.ok) {
                showLoginMessage(data?.message || 'Impossible de vérifier votre compte Discord actuellement.');
                return;
            }

            if (!data.authenticated) {
                showLoginMessage('Connectez-vous avec Discord (bouton Se connecter). Le ticket exige un compte Discord et la présence sur le serveur Synkrone.');
                return;
            }

            if (!data.isMember) {
                showJoinMessage(
                    'Votre compte est connecté, mais vous devez rejoindre le serveur Discord avant de contacter le support.'
                );
                return;
            }

            showTicketState(data?.cooldownSecondsRemaining);
        } catch (error) {
            console.error('Verification contact-state impossible:', error);
            showLoginMessage('Le service de vérification est indisponible. Réessayez dans un instant.');
        }
    }

    applyContactConfig();
    applyContactState();

    function setStatus(message, type) {
        statusEl.textContent = message;
        statusEl.classList.remove('success', 'error');
        if (type) {
            statusEl.classList.add(type);
        }
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!canSubmitTicket) {
            setStatus('Vous devez être autorisé avant d envoyer une demande au support.', 'error');
            return;
        }

        const theme = String(form.theme?.value || '').trim();
        const message = String(form.message?.value || '').trim();

        if (!theme || !message) {
            setStatus('Merci de remplir tous les champs obligatoires.', 'error');
            return;
        }

        setStatus('Envoi du ticket en cours...');

        try {
            const response = await fetch('/api/contact-ticket', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    theme,
                    message
                })
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok || !data.ok) {
                const errorMessage = data?.message || 'Erreur lors de l envoi du ticket.';
                setStatus(errorMessage, 'error');
                if (response.status === 429 && Number(data?.retryAfterSeconds || 0) > 0) {
                    setSubmitAvailability(true, Number(data.retryAfterSeconds));
                }
                return;
            }

            setStatus('Demande envoyée au support. Merci pour votre retour.', 'success');
            setSubmitAvailability(true, Number(data?.cooldownSecondsRemaining || 0));
            form.reset();
        } catch (error) {
            console.error('Erreur envoi ticket:', error);
            setStatus('Le serveur ne répond pas pour le moment. Réessayez plus tard.', 'error');
        }
    });
})();
