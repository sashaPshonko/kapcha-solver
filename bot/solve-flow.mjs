/**
 * Bot ↔ kapcha-solver: захват капчи → POST /api/solve → цифры в чат → /reg → /l
 *
 * Маркер: BotFilter >> Введите номер с картинки в чат
 *
 * Зависимости бота: mineflayer + flayercaptcha + pngjs (как в kapcha/).
 * Capture берётся из соседнего ../kapcha/lib (в монорепо).
 *
 *   import { handleCaptchaLogin } from '../kapcha-solver/bot/solve-flow.mjs';
 *   await handleCaptchaLogin(bot, { password, solverUrl });
 */

import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const KAPCHA_LIB = join(__dirname, '..', '..', 'kapcha', 'lib');

const require = createRequire(import.meta.url);

export const CAPTCHA_CHAT_MARKER = 'BotFilter >> Введите номер с картинки в чат';

export function isCaptchaChat(text) {
    const s = String(text || '').toLowerCase();
    return (
        s.includes('введите номер с картинки') ||
        s.includes(CAPTCHA_CHAT_MARKER.toLowerCase())
    );
}

/**
 * @param {string} solverUrl  e.g. http://1.2.3.4:8790
 * @param {{ pngBase64: string, username?: string, fingerprint?: string, timeoutMs?: number }} opts
 */
export async function solveRemote(solverUrl, opts) {
    const base = String(solverUrl || '').replace(/\/$/, '');
    if (!base) throw new Error('solverUrl empty');
    const headers = { 'Content-Type': 'application/json' };
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 20_000);
    try {
        const res = await fetch(`${base}/api/solve`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                pngBase64: opts.pngBase64,
                username: opts.username || undefined,
                fingerprint: opts.fingerprint || undefined,
            }),
            signal: ctrl.signal,
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(`solve HTTP ${res.status}: ${body.detail || JSON.stringify(body)}`);
        }
        if (!body.ok && body.low_conf) {
            // caller may refresh captcha; dump already on solver
            throw new Error(`low conf ${body.conf} pred=${body.pred} dump=${body.dump || '-'}`);
        }
        if (!body.pred || !/^\d{5}$/.test(body.pred)) {
            throw new Error(`bad pred ${JSON.stringify(body)}`);
        }
        return body;
    } finally {
        clearTimeout(t);
    }
}

async function loadCapture() {
    const { waitForCaptcha, attachMapCache } = await import(
        join(KAPCHA_LIB, 'capture.mjs')
    );
    return { waitForCaptcha, attachMapCache };
}

function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
}

/**
 * Полный цикл после появления капчи (или сразу на входе, если стена уже есть):
 * 1) собрать PNG с item-frame карт
 * 2) отправить на VPS solver
 * 3) написать 5 цифр в чат
 * 4) /reg <password>
 * 5) /l <password>
 *
 * @param {import('mineflayer').Bot} bot
 * @param {{
 *   password: string,
 *   solverUrl: string,
 *   username?: string,
 *   quietMs?: number,
 *   maxWaitMs?: number,
 *   afterAnswerMs?: number,
 *   afterRegMs?: number,
 *   log?: (...a:any[]) => void,
 * }} opts
 */
export async function handleCaptchaLogin(bot, opts) {
    const log = opts.log || ((...a) => console.log('[captcha]', ...a));
    const password = String(opts.password || '');
    if (!password) throw new Error('password required');

    const { waitForCaptcha, attachMapCache } = await loadCapture();
    attachMapCache(bot);

    log('waiting for captcha maps…');
    const captured = await waitForCaptcha(bot, {
        quietMs: opts.quietMs ?? 900,
        maxWaitMs: opts.maxWaitMs ?? 20_000,
        log,
    });
    if (!captured?.png) {
        throw new Error('captcha capture failed / timeout');
    }

    const pngBase64 = Buffer.isBuffer(captured.png)
        ? captured.png.toString('base64')
        : Buffer.from(captured.png).toString('base64');

    log('solving remote…', opts.solverUrl);
    const solved = await solveRemote(opts.solverUrl, {
        pngBase64,
        username: opts.username || bot.username,
        fingerprint: captured.fingerprint,
    });
    log('pred', solved.pred, 'conf', solved.conf, `${solved.ms}ms`);

    bot.chat(solved.pred);
    await sleep(opts.afterAnswerMs ?? 800);

    // тупо, но работает: сначала /reg, потом /l
    bot.chat(`/reg ${password}`);
    await sleep(opts.afterRegMs ?? 600);
    bot.chat(`/l ${password}`);

    return { pred: solved.pred, conf: solved.conf, ms: solved.ms };
}

/**
 * Подписка на чат: при маркере капчи один раз гоняет handleCaptchaLogin.
 * Возвращает disposer().
 */
export function watchCaptchaAndLogin(bot, opts) {
    let busy = false;
    const onMsg = async (text) => {
        if (!isCaptchaChat(text) || busy) return;
        busy = true;
        try {
            await handleCaptchaLogin(bot, opts);
        } catch (e) {
            (opts.log || console.error)('[captcha] fail', e);
            opts.onError?.(e);
        } finally {
            busy = false;
        }
    };
    // messagestr only — иначе message+messagestr сработают дважды
    const handler = (s) => {
        void onMsg(s);
    };
    bot.on('messagestr', handler);
    return () => bot.off('messagestr', handler);
}
