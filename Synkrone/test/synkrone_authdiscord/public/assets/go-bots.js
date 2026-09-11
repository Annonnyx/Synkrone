function goBots(event, tab) {
    if (event) event.preventDefault();
    const options = { subTab: 'bots', updateUrl: true };
    if (tab) options.botsTab = tab;
    try {
        if (window.parent && window.parent !== window && typeof window.parent.navigateToMainSection === 'function') {
            window.parent.navigateToMainSection('discord', options);
            return;
        }
    } catch {
        /* fall through */
    }
    const href = event && event.currentTarget && event.currentTarget.getAttribute('href');
    window.top.location.href = href || (tab ? '/discord/bots/' + tab : '/discord/bots');
}
