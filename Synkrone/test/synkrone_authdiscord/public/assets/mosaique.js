(() => {
    const BODY_CLASS = 'mosaic-bg';
    const LAYER_ID = 'mosaic-layer';
    const DEFAULT_LOGO = '/assets/images/logo.jpg';

    function getTileSize() {
        const value = getComputedStyle(document.documentElement)
            .getPropertyValue('--mosaic-tile-size')
            .trim();
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : 60;
    }

    function ensureLayer() {
        let layer = document.getElementById(LAYER_ID);
        if (!layer) {
            layer = document.createElement('div');
            layer.id = LAYER_ID;
            layer.className = 'mosaic-layer';
            layer.setAttribute('aria-hidden', 'true');
            document.body.prepend(layer);
        }
        return layer;
    }

    function buildMosaic() {
        if (!document.body.classList.contains(BODY_CLASS)) return;

        const layer = ensureLayer();
        const tileSize = getTileSize();
        const cols = Math.ceil(window.innerWidth / tileSize) + 1;
        const rows = Math.ceil(window.innerHeight / tileSize) + 1;
        const logoPath = document.body.dataset.mosaicLogo || DEFAULT_LOGO;
        const fragment = document.createDocumentFragment();

        for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
                const tile = document.createElement('img');
                tile.className = 'mosaic-tile';
                tile.src = logoPath;
                tile.alt = '';
                tile.style.left = `${col * tileSize}px`;
                tile.style.top = `${row * tileSize}px`;
                fragment.appendChild(tile);
            }
        }

        layer.replaceChildren(fragment);
    }

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(buildMosaic, 100);
    });

    window.addEventListener('DOMContentLoaded', buildMosaic);
})();
