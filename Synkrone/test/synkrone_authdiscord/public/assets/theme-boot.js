(function (global) {
    var KEY = "synkrone_theme";

    function readCookie() {
        var match = document.cookie.match(/(?:^|; )synkrone_theme=(light|dark)(?:;|$)/);
        return match ? match[1] : "";
    }

    function read() {
        var fromCookie = readCookie();
        if (fromCookie === "light" || fromCookie === "dark") return fromCookie;
        try {
            var stored = global.localStorage.getItem(KEY);
            if (stored === "light" || stored === "dark") return stored;
        } catch (err) {
            /* storage unavailable */
        }
        return "light";
    }

    function apply(theme) {
        var next = theme === "dark" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", next);
        document.documentElement.classList.toggle("dark", next === "dark");
        document.documentElement.style.colorScheme = next;
        return next;
    }

    function persist(theme) {
        var next = apply(theme);
        document.cookie = KEY + "=" + next + ";path=/;max-age=31536000;samesite=lax";
        try {
            global.localStorage.setItem(KEY, next);
        } catch (err) {
            /* storage unavailable */
        }
        try {
            global.dispatchEvent(new CustomEvent("synkrone-theme", { detail: next }));
        } catch (err) {
            /* CustomEvent unavailable */
        }
        return next;
    }

    function applyToFrame(frame) {
        if (!frame) return;
        try {
            var doc = frame.contentDocument;
            if (!doc || !doc.documentElement) return;
            var theme = read();
            doc.documentElement.setAttribute("data-theme", theme);
            doc.documentElement.classList.toggle("dark", theme === "dark");
            doc.documentElement.style.colorScheme = theme;
        } catch (err) {
            /* cross-origin or not ready */
        }
    }

    global.synkroneTheme = {
        key: KEY,
        read: read,
        apply: apply,
        set: persist,
        toggle: function () {
            return persist(read() === "dark" ? "light" : "dark");
        },
        applyToFrame: applyToFrame
    };

    apply(read());
})(window);
