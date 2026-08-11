// Phisherman AI v6 - Content Script
// Extracts page signals, renders trust overlay, guards forms

(function() {
  'use strict';

  // Prevent double-injection
  if (window.__phishermanInjected) return;
  window.__phishermanInjected = true;

  // --- Signal Extraction ---

  function extractSignals() {
    const forms = document.querySelectorAll('form');
    const inputs = document.querySelectorAll('input');
    const links = document.querySelectorAll('a[href]');

    let hasPassword = false;
    let hasEmail = false;
    let hasCreditCard = false;
    let hasLoginForm = false;
    let hasPaymentForm = false;
    const formActionHosts = [];

    inputs.forEach(input => {
      const type = (input.type || '').toLowerCase();
      const name = (input.name || '').toLowerCase();
      const autocomplete = (input.autocomplete || '').toLowerCase();

      if (type === 'password') hasPassword = true;
      if (type === 'email' || name.includes('email') || autocomplete === 'email') hasEmail = true;
      if (autocomplete.includes('cc-number') || name.includes('card') || name.includes('credit'))
        hasCreditCard = true;
    });

    forms.forEach(form => {
      const action = form.action || '';
      if (action && action.startsWith('http')) {
        try {
          const actionHost = new URL(action).hostname;
          const pageHost = window.location.hostname;
          if (actionHost !== pageHost) {
            formActionHosts.push(actionHost);
          }
        } catch {}
      }

      const formText = form.textContent.toLowerCase();
      const formInputs = form.querySelectorAll('input');
      let formHasPassword = false;
      let formHasEmail = false;

      formInputs.forEach(input => {
        if (input.type === 'password') formHasPassword = true;
        if (input.type === 'email' || (input.name || '').includes('email')) formHasEmail = true;
      });

      if (formHasPassword && (formHasEmail || formText.includes('sign in') || formText.includes('log in'))) {
        hasLoginForm = true;
      }

      if (hasCreditCard || formText.includes('payment') || formText.includes('checkout') ||
          formText.includes('billing')) {
        hasPaymentForm = true;
      }
    });

    // Link analysis
    const pageHost = window.location.hostname;
    const visibleLinkHostsSet = new Set();
    let externalLinkCount = 0;

    links.forEach(link => {
      try {
        const href = link.href;
        if (!href || !href.startsWith('http')) return;
        const linkHost = new URL(href).hostname;
        if (linkHost !== pageHost) {
          externalLinkCount++;
          if (link.offsetParent !== null) { // visible
            visibleLinkHostsSet.add(linkHost);
          }
        }
      } catch {}
    });

    return {
      hasPassword,
      hasEmail,
      hasCreditCard,
      hasLoginForm,
      hasPaymentForm,
      formActionHosts: [...new Set(formActionHosts)],
      visibleLinkHosts: [...visibleLinkHostsSet].slice(0, 20),
      externalLinkCount
    };
  }

  function extractVisibleText() {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const tag = node.parentElement?.tagName;
          if (!tag) return NodeFilter.FILTER_REJECT;
          if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG'].includes(tag)) return NodeFilter.FILTER_REJECT;
          if (node.textContent.trim().length === 0) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    let text = '';
    while (walker.nextNode()) {
      text += walker.currentNode.textContent.trim() + ' ';
      if (text.length > 15000) break;
    }
    return text.slice(0, 15000);
  }

  function detectNewsArticle() {
    // Check meta tags
    const ogType = document.querySelector('meta[property="og:type"]');
    if (ogType && ogType.content === 'article') return true;

    // Check schema.org
    const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of ldScripts) {
      try {
        const data = JSON.parse(script.textContent);
        const types = Array.isArray(data['@type']) ? data['@type'] : [data['@type']];
        if (types.some(t => t && (t.includes('NewsArticle') || t.includes('Article')))) return true;
      } catch {}
    }

    // Check semantic elements
    const hasArticle = document.querySelector('article') !== null;
    const hasTime = document.querySelector('time[datetime]') !== null;
    const hasAuthor = document.querySelector('[rel="author"], .author, .byline, meta[name="author"]') !== null;

    return hasArticle && (hasTime || hasAuthor);
  }

  function extractUrlsFromText(text) {
    const links = new Set();
    const httpMatches = text.match(/https?:\/\/[^\s]+/g) || [];
    const bareMatches = text.match(/(?:www\.|bit\.ly\/|tinyurl\.com\/|cutt\.ly\/|rb\.gy\/|is\.gd\/)[^\s]+/g) || [];
    httpMatches.forEach(link => links.add(link));
    bareMatches.forEach(link => links.add(link.startsWith('http') ? link : `https://${link}`));
    return [...links].slice(0, 10);
  }

  function normalizeText(text) {
    return (text || '').replace(/\s+/g, ' ').trim();
  }

  function truncateText(text, maxLength = 240) {
    const normalized = normalizeText(text);
    if (normalized.length <= maxLength) return normalized;
    return `${normalized.slice(0, maxLength - 1)}…`;
  }

  function getElementText(el, maxLength = 1200) {
    if (!el) return '';
    return truncateText(el.innerText || el.textContent || '', maxLength);
  }

  function getSelectionRootNode(selection) {
    const node = selection?.anchorNode;
    if (!node) return null;
    return node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  }

  function findContextContainer(el) {
    return el?.closest?.(
      '[data-id], article, section, main, p, li, blockquote, div[role="row"], div[role="listitem"], div[dir="auto"]'
    ) || el?.parentElement || null;
  }

  function getNearbyText(el) {
    const container = findContextContainer(el);
    return {
      contextType: container?.getAttribute?.('data-id') ? 'message' : (container?.tagName || 'element').toLowerCase(),
      surroundingText: getElementText(container, 1400),
      containerTag: (container?.tagName || '').toLowerCase(),
    };
  }

  function getImageCaption(img) {
    const figure = img.closest('figure');
    const figcaption = figure?.querySelector('figcaption');
    if (figcaption) return truncateText(figcaption.textContent, 220);

    const labelledBy = img.getAttribute('aria-labelledby');
    if (labelledBy) {
      const label = document.getElementById(labelledBy);
      if (label?.textContent) return truncateText(label.textContent, 220);
    }

    const parentText = truncateText(img.parentElement?.innerText || '', 220);
    const ownAlt = normalizeText(img.alt || img.title || '');
    if (parentText && parentText !== ownAlt) return parentText;
    return '';
  }

  function extractVisibleMedia(maxItems = 6) {
    const media = [];
    const images = [...document.images].filter(img => {
      if (!img.src || img.offsetParent === null) return false;
      return (img.naturalWidth || img.width || 0) >= 64 && (img.naturalHeight || img.height || 0) >= 64;
    }).slice(0, maxItems);

    images.forEach((img, index) => {
      let host = '';
      try {
        host = new URL(img.currentSrc || img.src, window.location.href).hostname;
      } catch {}

      media.push({
        id: img.id || `img-${index}`,
        alt: truncateText(img.alt || img.title || '', 200),
        caption: getImageCaption(img),
        width: img.naturalWidth || img.width || 0,
        height: img.naturalHeight || img.height || 0,
        srcHost: host,
        role: img.getAttribute('role') || '',
      });
    });

    return media;
  }

  async function detectVisibleQRCodes(maxItems = 4) {
    if (typeof BarcodeDetector === 'undefined') return [];

    let detector;
    try {
      detector = new BarcodeDetector({ formats: ['qr_code'] });
    } catch {
      return [];
    }

    const candidates = [...document.querySelectorAll('img, canvas')].filter(el => {
      if (el.offsetParent === null) return false;
      const width = el.naturalWidth || el.width || 0;
      const height = el.naturalHeight || el.height || 0;
      return width >= 80 && height >= 80;
    }).slice(0, 12);

    const qrResults = [];
    for (const el of candidates) {
      if (qrResults.length >= maxItems) break;
      try {
        const matches = await detector.detect(el);
        matches.forEach((match) => {
          if (!match?.rawValue) return;
          const rawValue = truncateText(match.rawValue, 320);
          if (qrResults.some(item => item.rawValue === rawValue)) return;

          let linkHost = '';
          let contentType = 'text';
          try {
            const parsed = new URL(match.rawValue);
            linkHost = parsed.hostname;
            contentType = parsed.protocol.startsWith('http') ? 'url' : parsed.protocol.replace(':', '');
          } catch {
            if (/^[\w.\-]+@[\w.\-]+$/.test(match.rawValue)) contentType = 'upi-or-id';
          }

          qrResults.push({
            rawValue,
            format: match.format || 'qr_code',
            contentType,
            host: linkHost,
            nearbyText: getImageCaption(el) || truncateText(el.parentElement?.innerText || '', 200),
          });
        });
      } catch {}
    }

    return qrResults;
  }

  function getWhatsAppChatTitle() {
    const titleCandidates = [
      document.querySelector('#main header [title]'),
      document.querySelector('#main header span[dir="auto"]'),
      document.querySelector('header [data-testid="conversation-info-header-chat-title"]'),
    ];
    for (const el of titleCandidates) {
      const title = el?.getAttribute('title') || el?.textContent?.trim();
      if (title) return title;
    }
    return 'WhatsApp Chat';
  }

  // ─── Webmail Message Extractor ───────────────────────────────────────────
  //
  // WHY THIS EXISTS - and why it fails CLOSED.
  //
  // extractVisibleText() walks all of document.body. On a webmail SPA that is
  // not the open email: Gmail keeps the thread list mounted behind the reading
  // pane, so the text being scored was ~50 other people's promotional subject
  // lines. A legitimate internship email was reported as "Lottery/prize scam"
  // + "Personal information request" + "Excessive exclamation marks (9)" - the
  // email contained zero exclamation marks. The evidence came from Swiggy and
  // Cred promos three rows down the inbox, and the verdict was titled with the
  // open message. That is a G-2 false accusation manufactured by scope alone.
  //
  // So on a known mail host the unit of judgement is the OPEN MESSAGE. If we
  // cannot isolate it, we return a sentinel that suppresses scoring rather than
  // falling back to the whole page. Failing open here is precisely the bug:
  // "no verdict" is honest, "your real mail is a scam" is not.
  //
  // Selectors are attribute-first and tiered, in the same discipline as
  // whatsapp/selectors.js. They are NOT verified against live Gmail/Outlook
  // DOM - but the failure mode is, which is what makes shipping this safe.

  const MAIL_HOSTS = /(?:^|\.)(?:mail\.google\.com|outlook\.(?:live|office|office365)\.com|outlook\.com|mail\.yahoo\.com|mail\.proton\.me|mail\.zoho\.com|roundcube|webmail)/i;

  const MAIL_BODY_SELECTORS = [
    // Gmail - data-message-id is the stable hook; .a3s is the body container.
    '[data-message-id] .a3s',
    '[data-legacy-message-id] .a3s',
    'div[role="listitem"] [data-message-id]',
    // Outlook web
    '[aria-label="Message body"]',
    'div[id^="UniqueMessageBody"]',
    // Yahoo / Proton / Zoho
    '[data-test-id="message-view-body"]',
    '[data-testid="message-content"]',
    'iframe[title="Email content"]',
  ];

  const MAIL_SUBJECT_SELECTORS = [
    'h2[data-thread-perm-id]',
    '[role="main"] h2',
    '[aria-label="Message subject"]',
    '[data-test-id="message-subject"]',
  ];

  const MAIL_SENDER_SELECTORS = [
    '[data-message-id] span[email]',
    'span[email]',
    '[data-test-id="message-from"]',
    '[aria-label*="Sender"]',
  ];

  function isMailHost() {
    return MAIL_HOSTS.test(window.location.hostname);
  }

  function firstMatch(selectors) {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el) return el;
      } catch { /* invalid selector on this host — try the next tier */ }
    }
    return null;
  }

  function extractMailMessage() {
    if (!isMailHost()) return null;

    // Only the LAST body node: with a quoted thread expanded, Gmail mounts every
    // earlier message too, and scoring all of them re-imports the same
    // cross-message contamination at a smaller scale.
    let bodyEl = null;
    for (const sel of MAIL_BODY_SELECTORS) {
      try {
        const all = document.querySelectorAll(sel);
        if (all.length) { bodyEl = all[all.length - 1]; break; }
      } catch { /* next tier */ }
    }

    if (!bodyEl) {
      // Isolation failed. Do not score the page.
      return { source: 'webmail', isolated: false, text: '', scannable: false };
    }

    // Drop quoted history and the trailing signature so a scam quoted INTO a
    // reply is not scored as if the sender wrote it.
    const clone = bodyEl.cloneNode(true);
    clone.querySelectorAll(
      '.gmail_quote, blockquote, .gmail_signature, [data-smartmail="gmail_signature"], .moz-cite-prefix'
    ).forEach((n) => n.remove());

    const text = (clone.innerText || clone.textContent || '').trim();
    const subjectEl = firstMatch(MAIL_SUBJECT_SELECTORS);
    const senderEl = firstMatch(MAIL_SENDER_SELECTORS);
    const sender = senderEl?.getAttribute?.('email') || senderEl?.textContent?.trim() || '';
    const subject = subjectEl?.textContent?.trim() || '';

    const links = [...bodyEl.querySelectorAll('a[href]')]
      .map((a) => a.getAttribute('href'))
      .filter((h) => h && /^https?:/i.test(h))
      .slice(0, 20);

    return {
      source: 'webmail',
      isolated: true,
      scannable: text.length > 0,
      subject,
      sender,
      // Subject is part of the message; the sender address is NOT included in
      // the scored text - it is an identity fact, and feeding it to the content
      // scorer is what made every mail page report a UPI handle.
      text: [subject, text].filter(Boolean).join('\n\n').slice(0, 15000),
      links,
    };
  }

  // ─── WhatsApp Web Message Extractor ──────────────────────────────────────
  // Reads recent incoming messages from WhatsApp Web DOM.
  // Returns text + links for local gate + backend analysis.

  function extractWhatsAppMessages() {
    if (!window.location.hostname.includes('web.whatsapp.com')) return null;

    const records = [];
    const links = new Set();
    const bubbleSelector = '#main [data-id].message-in, #main [data-id][data-testid*="msg-in"], #main [data-id]';
    const bubbles = [...document.querySelectorAll(bubbleSelector)].slice(-24);

    const attachments = [];

    bubbles.forEach((bubble, index) => {
      const textNodes = bubble.querySelectorAll('.selectable-text, [data-testid="msg-text"], [class*="selectable-text"]');
      const text = [...textNodes]
        .map(node => node.innerText?.trim() || '')
        .filter(Boolean)
        .join('\n')
        .trim();

      // A file bubble has NO .selectable-text node, so the length check below
      // discarded it before anything could look at it - an APK attachment was
      // invisible to this whole path while the panel reported the chat SAFE.
      // Read the attachment first, and never let a bubble carrying one be
      // dropped for having no message text.
      const attachment = PhishermanApkCheck.readAttachmentFrom(bubble, { source: 'chat' });
      if (attachment) {
        attachments.push({
          ...attachment,
          message_id: bubble.getAttribute('data-id') || `wa-msg-${index}`,
        });
      }

      if (!attachment && (!text || text.length < 5)) return;

      const bubbleText = bubble.innerText?.toLowerCase() || '';
      const messageId = bubble.getAttribute('data-id') || `wa-msg-${index}`;
      const isIncoming = bubble.classList.contains('message-in')
        || bubble.getAttribute('data-testid')?.includes('msg-in')
        || !bubble.classList.contains('message-out');
      const isForwarded = bubbleText.includes('forwarded');
      const messageLinks = extractUrlsFromText(text);
      messageLinks.forEach(link => links.add(link));

      records.push({
        id: messageId,
        text,
        isIncoming,
        isForwarded,
        links: messageLinks,
        attachment: attachment || null,
      });
    });

    const recentIncoming = records.filter(record => record.isIncoming).slice(-8);
    // An attachment alone is enough to return a payload. Requiring message text
    // here is what made a chat whose only risky content was a file bubble come
    // back as "no messages" and fall through to the generic page scan.
    if (recentIncoming.length === 0 && attachments.length === 0) return null;

    return {
      source: 'whatsapp-web',
      chatTitle: getWhatsAppChatTitle(),
      messageCount: recentIncoming.length,
      text: recentIncoming.map(record => record.text).join('\n'),
      links: [...links].slice(0, 10),
      records: recentIncoming,
      attachments,
    };
  }

  // ─── Telegram Web Message Extractor ──────────────────────────────────────
  function extractTelegramMessages() {
    if (!window.location.hostname.includes('web.telegram.org')) return null;

    const messages = [];
    const msgEls = document.querySelectorAll('.message.spoilers-container, .text-content');
    msgEls.forEach(el => {
      if (messages.length >= 20) return;
      const text = el.innerText?.trim();
      if (text && text.length > 5) messages.push(text);
    });

    if (messages.length === 0) return null;
    return {
      source: 'telegram-web',
      messageCount: messages.length,
      text: messages.join('\n'),
    };
  }

  function buildSnapshot() {
    const signals = extractSignals();
    const isNewsArticle = detectNewsArticle();

    // WhatsApp / Telegram / webmail: score the MESSAGE, not the page around it.
    const waData = extractWhatsAppMessages();
    const tgData = extractTelegramMessages();
    const mailData = extractMailMessage();
    const messagingData = waData || tgData || (mailData?.isolated ? mailData : null);

    let visibleText;
    let scannable = true;
    if (messagingData) {
      visibleText = messagingData.text;
      scannable = messagingData.scannable !== false;
    } else if (mailData) {
      // Known mail host, message could not be isolated. Scoring the whole SPA
      // here is the defect this branch exists to prevent - return nothing and
      // let the background suppress the verdict.
      visibleText = '';
      scannable = false;
    } else {
      visibleText = extractVisibleText();
    }

    return {
      url: window.location.href,
      title: document.title,
      domain: window.location.hostname,
      visibleText,
      pageText: visibleText,
      scannable,
      scanScope: messagingData ? messagingData.source : (mailData ? 'webmail-unisolated' : 'page'),
      // Filename-only, read from the rendered label. Analysed on-device in the
      // service worker so an APK offer is still flagged with the backend down.
      attachments: (messagingData && messagingData.attachments) || [],
      isNewsArticle,
      signals,
      messaging: messagingData || null,
      meta: {
        description: document.querySelector('meta[name="description"]')?.content || '',
        ogTitle: document.querySelector('meta[property="og:title"]')?.content || '',
        ogDescription: document.querySelector('meta[property="og:description"]')?.content || ''
      },
      timestamp: Date.now()
    };
  }

  async function buildSelectionSnapshot(selectedTextOverride = '') {
    const selection = window.getSelection();
    const selectedText = normalizeText(selectedTextOverride || selection?.toString() || '');
    if (!selectedText || selectedText.length < 12) return null;

    const snapshot = buildSnapshot();
    const root = getSelectionRootNode(selection);
    const nearby = getNearbyText(root);
    const media = extractVisibleMedia();
    const qrCodes = await detectVisibleQRCodes();

    return {
      ...snapshot,
      selection: {
        text: selectedText,
        ...nearby,
      },
      visibleText: selectedText,
      pageText: [selectedText, nearby.surroundingText, snapshot.pageText].filter(Boolean).join('\n\n').slice(0, 18000),
      media,
      qrCodes,
    };
  }

  // --- Trust Island ---
  //
  // Rebuilt as a shadow-DOM component. The previous version appended a plain
  // <div> to document.body with per-element inline styles and then wired its
  // buttons with document.getElementById(...). Three consequences, all real:
  //
  //   * Page CSS applied to it. Any site with `div { }` rules, a global
  //     transition, or `* { font-family }` restyled the warning.
  //   * getElementById searched the PAGE document, so a page containing an
  //     element with our id captured our click handlers.
  //   * getOverlayLayout() read window.innerWidth once, at creation. Resizing
  //     or rotating left the island positioned for the old viewport.
  //
  // Styles now live in one adopted stylesheet inside a closed-ish shadow root,
  // handlers bind to nodes we hold references to, and layout is recomputed on
  // resize through a ResizeObserver-free rAF-throttled listener.
  //
  // Motion is opacity+transform only (compositor-driven, no layout), 160ms, and
  // is skipped entirely under prefers-reduced-motion.

  const ISLAND_HOST_ID = 'phisherman-trust-island';
  let overlayEl = null;       // presence flag read by other call sites in this file
  let islandHost = null;      // the host element in the page
  let islandRoot = null;      // its shadow root
  let islandRefs = null;      // { card, ... } - direct refs, never getElementById
  let islandTimeout = null;
  let islandResizeRaf = 0;

  const ISLAND_CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .card {
      position: fixed; z-index: 2147483647;
      /* 360 -> 300. The island is a glance surface that sits on top of
         somebody else's UI; it needs to be readable, not roomy. */
      width: min(300px, calc(100vw - 32px));
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      color: #dbe7ff;
      background:
        radial-gradient(circle at top left, rgba(59,130,246,.16), transparent 36%),
        linear-gradient(180deg, rgba(15,23,42,.98), rgba(15,23,42,.94));
      border: 1px solid var(--accent-dim, rgba(148,163,184,.3));
      border-radius: 14px; padding: 11px;
      box-shadow: 0 18px 48px rgba(2,6,23,.42);
      backdrop-filter: blur(14px);
      opacity: 0;
      /* Only opacity+transform animate: both run on the compositor, so the
         island never triggers layout on the host page while appearing. */
      transition: opacity .16s ease-out, transform .16s ease-out;
      will-change: opacity, transform;
      contain: content;
    }
    .card.pos-bottom-right { bottom: 18px; right: 18px; transform: translateY(8px); }
    .card.pos-bottom-left  { bottom: 18px; left: 18px;  transform: translateY(8px); }
    .card.pos-top-right    { top: 18px;    right: 18px; transform: translateY(-8px); }
    .card.pos-compact {
      left: 50%; right: auto; bottom: 16px; width: min(92vw, 300px);
      transform: translate(-50%, 8px);
    }
    .card.in                 { opacity: 1; transform: translateY(0); }
    .card.pos-compact.in     { opacity: 1; transform: translate(-50%, 0); }
    @media (prefers-reduced-motion: reduce) {
      .card { transition: none; }
    }

    .head { display: flex; align-items: flex-start; gap: 10px; }
    .score {
      width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
      border: 3px solid var(--accent); color: var(--accent);
      background: var(--accent-wash);
      display: flex; align-items: center; justify-content: center;
      font-size: 15px; font-weight: 800; font-variant-numeric: tabular-nums;
    }
    .meta { min-width: 0; flex: 1; }
    .badge {
      display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 999px;
      background: var(--accent-wash); color: var(--accent);
      font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em;
      margin-bottom: 5px;
    }
    .headline { font-size: 13px; font-weight: 700; color: #f8fbff; line-height: 1.3; }
    .brand { font-size: 10px; color: #8da2c0; margin-top: 3px; }
    .close {
      margin-left: auto; width: 24px; height: 24px; border-radius: 999px; flex-shrink: 0;
      background: rgba(148,163,184,.08); border: 1px solid rgba(148,163,184,.14);
      color: #8da2c0; cursor: pointer; font-size: 14px; line-height: 1; padding: 0;
    }
    .close:hover { background: rgba(148,163,184,.18); color: #dbe7ff; }
    .close:focus-visible, .btn:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }

    .signals { margin: 9px 0 7px; display: flex; flex-direction: column; gap: 5px; }
    .sig {
      display: flex; align-items: flex-start; gap: 7px; padding: 7px 9px;
      border-radius: 9px; background: rgba(15,23,42,.8);
      border: 1px solid rgba(148,163,184,.12);
    }
    .sig-icon {
      width: 16px; height: 16px; border-radius: 999px; flex-shrink: 0;
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: 700;
    }
    .sig-text { font-size: 11.5px; line-height: 1.4; }
    /* Severity belongs to the SIGNAL. A protective fact rendered in risk colours
       tells the user the opposite of what the engine found - see
       shared/signal_polarity.js. */
    .sev-high   .sig-icon { color: #fca5a5; background: rgba(252,165,165,.13); }
    .sev-medium .sig-icon { color: #fcd34d; background: rgba(252,211,77,.13); }
    .sev-low    .sig-icon { color: #93c5fd; background: rgba(147,197,253,.13); }
    .pol-protective .sig-icon { color: #86efac; background: rgba(134,239,172,.13); }
    .pol-protective { border-color: rgba(134,239,172,.25); }
    .pol-context .sig-icon { color: #94a3b8; background: rgba(148,163,184,.13); }

    .actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
    .btn {
      padding: 7px 11px; border-radius: 9px; cursor: pointer;
      font-size: 10.5px; font-weight: 700; font-family: inherit; border: 1px solid transparent;
    }
    .btn-primary { background: var(--accent); color: #081120; border-color: var(--accent); }
    .btn-ghost {
      background: rgba(148,163,184,.12); color: #dbe7ff;
      border-color: rgba(148,163,184,.18); font-weight: 600;
    }
  `;

  function islandPositionClass(position) {
    // Recomputed on every resize, not captured once at creation.
    const w = window.innerWidth || 1280;
    const messaging = /web\.whatsapp\.com|web\.telegram\.org/.test(window.location.hostname);
    // `pos-compact` centres the card horizontally. On a phone-width viewport
    // that is right; on a 1900px WhatsApp Web window it drops the card into
    // the middle of the message column, directly over the conversation the
    // user is trying to read. Centre only when the viewport is genuinely
    // narrow, and dock to the corner otherwise - on messaging sites that
    // corner is bottom-LEFT, because the bottom-right of a chat client is
    // the composer, the send button and the emoji tray.
    if (w <= 900) return 'pos-compact';
    if (messaging) return 'pos-bottom-left';
    const allowed = { 'top-right': 1, 'bottom-right': 1, 'bottom-left': 1 };
    return 'pos-' + (allowed[position] ? position : 'bottom-right');
  }

  function applyIslandPosition() {
    if (!islandRefs) return;
    const cls = islandPositionClass(islandRefs.position);
    if (cls === islandRefs.positionClass) return;      // no write unless it changed
    islandRefs.card.classList.remove('pos-compact', 'pos-top-right',
                                     'pos-bottom-right', 'pos-bottom-left');
    islandRefs.card.classList.add(cls);
    islandRefs.positionClass = cls;
  }

  function onIslandResize() {
    if (islandResizeRaf) return;                        // coalesce a resize burst
    islandResizeRaf = requestAnimationFrame(() => {
      islandResizeRaf = 0;
      applyIslandPosition();
    });
  }

  function onIslandKey(e) {
    if (e.key === 'Escape' && islandHost) removeOverlay();
  }

  function createOverlay(assessment, settings) {
    removeOverlay();

    const score = Math.round(assessment.trustScore);
    const level = assessment.riskLevel;
    const color = getTrustColor(score);
    const position = settings?.overlayPosition || 'bottom-right';
    const autoHide = settings?.overlayAutoHide ?? 10000;

    // Risks first, most severe first; protective facts last. Same classifier the
    // side panel uses, so the two surfaces cannot disagree about a signal.
    const parts = PhishermanSignalPolarity.partition(assessment.signals || []);
    const shown = parts.risk.concat(parts.context, parts.protective).slice(0, 3);

    const riskCopy = level === 'DANGER' ? 'High-risk scam indicators'
      : level === 'WARNING' ? 'Suspicious patterns detected'
        : level === 'CAUTION' ? 'Review before you trust'
          : 'No strong threat signal';

    islandHost = document.createElement('div');
    islandHost.id = ISLAND_HOST_ID;
    // The host is inert: everything visible lives in the shadow root, so page
    // stylesheets have nothing of ours to match against.
    islandHost.style.cssText = 'all: initial; position: static;';
    islandRoot = islandHost.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = ISLAND_CSS;

    const card = document.createElement('div');
    card.className = 'card ' + islandPositionClass(position);
    card.setAttribute('role', 'status');
    card.setAttribute('aria-live', 'polite');
    card.style.setProperty('--accent', color);
    card.style.setProperty('--accent-wash', color + '16');
    card.style.setProperty('--accent-dim', color + '55');

    const sigHTML = shown.map((s) => {
      const icon = s.polarity === 'protective' ? '✓'
        : s.polarity === 'context' ? 'i'
          : s.severity === 'high' ? '!' : s.severity === 'medium' ? '~' : 'i';
      const cls = s.polarity === 'risk' ? 'sev-' + s.severity : 'pol-' + s.polarity;
      return `<div class="sig ${cls}"><span class="sig-icon">${icon}</span>`
           + `<span class="sig-text">${escapeHtml(s.label)}</span></div>`;
    }).join('');

    card.innerHTML = `
      <div class="head">
        <div class="score">${score}</div>
        <div class="meta">
          <div class="badge">${escapeHtml(level)}</div>
          <div class="headline">${escapeHtml(riskCopy)}</div>
          <div class="brand">Phisherman AI Trust</div>
        </div>
        <button class="close" type="button" aria-label="Dismiss">&times;</button>
      </div>
      ${sigHTML ? `<div class="signals">${sigHTML}</div>` : ''}
      <div class="actions">
        ${assessment.isNewsArticle ? '<button class="btn btn-ghost" data-act="factcheck" type="button">Fact Check</button>' : ''}
        <button class="btn btn-primary" data-act="details" type="button">Details</button>
      </div>
    `;

    islandRoot.append(style, card);
    document.body.appendChild(islandHost);

    islandRefs = { card, position, positionClass: card.className.split(' ').pop() };

    // Handlers bind to nodes inside OUR shadow root. The previous version used
    // document.getElementById, which searches the page and can be shadowed by it.
    card.querySelector('.close').addEventListener('click', () => removeOverlay());
    card.querySelector('[data-act="details"]').addEventListener('click', () => {
      chrome.runtime.sendMessage({ action: 'openSidePanel' });
    });
    const fcBtn = card.querySelector('[data-act="factcheck"]');
    if (fcBtn) {
      fcBtn.addEventListener('click', async () => {
        fcBtn.textContent = 'Checking…';
        fcBtn.disabled = true;
        const snapshot = buildSnapshot();
        const result = await chrome.runtime.sendMessage({
          action: 'factCheck',
          payload: {
            url: snapshot.url, title: snapshot.title,
            text: snapshot.visibleText, domain: snapshot.domain,
          },
        });
        fcBtn.textContent = result ? 'Done' : 'Failed';
      });
    }

    window.addEventListener('resize', onIslandResize, { passive: true });
    window.addEventListener('keydown', onIslandKey);

    // One frame to let the initial (transparent, offset) state paint, then flip
    // the class. Two rAFs would be a frame slower for no benefit here.
    requestAnimationFrame(() => card.classList.add('in'));

    if (autoHide && autoHide > 0) {
      islandTimeout = setTimeout(() => removeOverlay(), autoHide);
    }

    overlayEl = islandHost;   // retained: other call sites test this for presence
  }

  function removeOverlay() {
    if (islandTimeout) { clearTimeout(islandTimeout); islandTimeout = null; }
    if (islandResizeRaf) { cancelAnimationFrame(islandResizeRaf); islandResizeRaf = 0; }
    window.removeEventListener('resize', onIslandResize);
    window.removeEventListener('keydown', onIslandKey);

    const host = islandHost;
    const refs = islandRefs;
    islandHost = null; islandRoot = null; islandRefs = null; overlayEl = null;
    if (!host) return;

    if (!refs || !refs.card || !host.isConnected) { host.remove(); return; }

    refs.card.classList.remove('in');
    // Remove when the fade actually ends rather than on a fixed timer that has
    // to be kept in sync with the CSS duration by hand.
    let done = false;
    const finish = () => { if (!done) { done = true; host.remove(); } };
    refs.card.addEventListener('transitionend', finish, { once: true });
    setTimeout(finish, 300);   // backstop if the transition never fires
  }

  function getTrustColor(score) {
    if (score >= 80) return '#22c55e';
    if (score >= 50) return '#eab308';
    if (score >= 25) return '#f97316';
    return '#ef4444';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Third copy of the "severity from the page score" defect, after background.js
  // and panel.js. A signal's meaning is a property of the signal - deriving it
  // from the aggregate paints protective facts as threats. One classifier now,
  // shared by all three surfaces: shared/signal_polarity.js.
  function normalizeSignal(signal) {
    return PhishermanSignalPolarity.normalise(signal);
  }

  function summarizeMessage(text, maxLength = 140) {
    const clean = (text || '').replace(/\s+/g, ' ').trim();
    if (clean.length <= maxLength) return clean;
    return `${clean.slice(0, maxLength - 1)}…`;
  }

  // --- Submit Guard ---

  function installSubmitGuard() {
    document.addEventListener('submit', (e) => {
      const cached = window.__phishermanLastAssessment;
      if (!cached || cached.riskLevel !== 'DANGER') return;

      e.preventDefault();
      e.stopImmediatePropagation();

      const confirmed = confirm(
        `\u26a0\ufe0f Phisherman AI Trust Warning\n\n` +
        `This page has a DANGER trust score (${Math.round(cached.trustScore)}/100).\n\n` +
        `Detected risks:\n` +
        (cached.signals || []).slice(0, 3).map(s => `  \u2022 ${s.label || s.message || 'Risk detected'}`).join('\n') +
        `\n\nAre you sure you want to submit this form?`
      );

      if (confirmed) {
        e.target.submit();
      }
    }, true);
  }

  // --- Link Hover Card ---
  //
  // Replaces a tooltip that printed the hostname and nothing else. Hovering a
  // link is the moment the user is deciding whether to click it, and it is the
  // last moment at which a warning can still prevent the click rather than
  // explain it afterwards - so it is worth spending the analysis there.
  //
  // The card renders in TWO STAGES so it is never waiting on the network:
  //
  //   1. Immediately (sub-millisecond, no network): the offline preflight -
  //      real registrable domain via the Public Suffix List, punycode and
  //      homoglyph findings, IP-literal and userinfo tricks, SEBI register
  //      resolution for securities links, shortener detection.
  //   2. If the link is a shortener AND the user enabled destination checking:
  //      the resolved redirect chain is patched in when it arrives.
  //
  // Stage 2 is opt-in and refuses one-time-token links outright - see
  // preflight/fetcher.js for why that refusal is not negotiable.
  //
  // Shadow DOM, for the same reason as the island: this renders on pages whose
  // CSS we do not control, and a warning restyled by the page it is warning
  // about is worse than no warning.

  const HOVER_DELAY_MS = 180;      // dwell before we do anything at all
  const HOVER_HIDE_MS = 120;       // grace period, so moving to the card is possible

  let hoverHost = null;            // shadow host element
  let hoverRefs = null;            // { card, body } - direct refs, never getElementById
  let hoverShowTimer = null;
  let hoverHideTimer = null;
  let hoverAnchor = null;
  let hoverToken = 0;              // guards against a stale async response

  const HOVER_CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .card {
      position: fixed; z-index: 2147483646;
      max-width: min(360px, calc(100vw - 24px));
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      font-size: 12px; line-height: 1.45; color: #dbe7ff;
      background: linear-gradient(180deg, rgba(15,23,42,.98), rgba(15,23,42,.95));
      border: 1px solid var(--accent, rgba(148,163,184,.35));
      border-radius: 12px; padding: 10px 12px;
      box-shadow: 0 12px 32px rgba(2,6,23,.45);
      backdrop-filter: blur(10px);
      opacity: 0; transform: translateY(4px);
      transition: opacity .12s ease-out, transform .12s ease-out;
      will-change: opacity, transform;
    }
    .card.in { opacity: 1; transform: translateY(0); }
    @media (prefers-reduced-motion: reduce) { .card { transition: none; } }

    .row { display: flex; align-items: baseline; gap: 8px; }
    .tag {
      flex-shrink: 0; padding: 2px 7px; border-radius: 999px;
      background: var(--accent-wash); color: var(--accent);
      font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    }
    .host {
      font-weight: 700; color: #f8fbff; word-break: break-all;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
    }
    .summary { margin-top: 6px; color: #cbd5e1; }
    .chain { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(148,163,184,.16); }
    .hop {
      display: flex; gap: 6px; align-items: baseline;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px; color: #94a3b8;
    }
    .hop + .hop { margin-top: 2px; }
    .hop .n { color: #64748b; flex-shrink: 0; }
    .hop.final .h { color: #f8fbff; font-weight: 700; }
    .sig { margin-top: 6px; display: flex; gap: 6px; align-items: flex-start; }
    .sig .dot { flex-shrink: 0; width: 14px; text-align: center; font-weight: 700; }
    .sev-high .dot { color: #fca5a5; }
    .sev-medium .dot { color: #fcd34d; }
    .sev-low .dot, .sev-none .dot { color: #93c5fd; }
    .muted { color: #8da2c0; font-size: 11px; margin-top: 6px; }
    .pending { color: #8da2c0; font-style: italic; }
    .checked { color: #94a3b8; font-size: 11px; line-height: 1.4; }
    .pol-protective .dot { color: #86efac; }
    .govlinks { font-size: 11px; }
    .govlinks a { color: #93c5fd; text-decoration: underline; text-underline-offset: 2px; }
    .govlinks a:hover { color: #bfdbfe; }
  `;

  // Verdict -> colour + label. Local names, so the card is legible without the
  // side panel open.
  const HOVER_VERDICTS = {
    L5_KNOWN_BAD:             { c: '#ef4444', t: 'Known bad' },
    L4_IDENTITY_MISMATCH:     { c: '#ef4444', t: 'Identity mismatch' },
    L3_PAYMENT_RISK:          { c: '#f97316', t: 'Payment risk' },
    L2_INFRASTRUCTURE_RISK:   { c: '#eab308', t: 'Address risk' },
    L1_UNVERIFIED_SECURITIES: { c: '#eab308', t: 'Unverified' },
    // "No signals" as a headline is a shrug. The tag says an action was taken;
    // the body says what it covered and what it did not.
    L0_NO_SIGNALS:            { c: '#64748b', t: 'Checked' },
  };

  function installLinkHoverTooltips() {
    document.addEventListener('mouseover', onHoverIn, true);
    document.addEventListener('mouseout', onHoverOut, true);
    // Keyboard users reach links by focus, not by pointer. The old tooltip was
    // pointer-only, so the warning did not exist for them at all.
    document.addEventListener('focusin', onHoverIn, true);
    document.addEventListener('focusout', onHoverOut, true);
    window.addEventListener('scroll', hideHoverCard, { passive: true, capture: true });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hideHoverCard();
    }, true);
  }

  function hoverableLink(target) {
    if (!target || typeof target.closest !== 'function') return null;
    const a = target.closest('a[href]');
    if (!a) return null;
    let href = '';
    try { href = a.href || ''; } catch { return null; }
    if (!/^https?:/i.test(href)) return null;
    return { a, href };
  }

  function onHoverIn(e) {
    const hit = hoverableLink(e.target);
    if (!hit) return;
    clearTimeout(hoverHideTimer);
    if (hoverAnchor === hit.a) return;          // already showing for this link
    clearTimeout(hoverShowTimer);
    hoverShowTimer = setTimeout(() => showHoverCard(hit.a, hit.href), HOVER_DELAY_MS);
  }

  function onHoverOut(e) {
    if (!hoverableLink(e.target)) return;
    clearTimeout(hoverShowTimer);
    clearTimeout(hoverHideTimer);
    hoverHideTimer = setTimeout(hideHoverCard, HOVER_HIDE_MS);
  }

  function ensureHoverCard() {
    if (hoverHost && hoverHost.isConnected) return hoverRefs;
    hoverHost = document.createElement('div');
    hoverHost.id = 'phisherman-hover-card';
    hoverHost.style.cssText = 'all: initial; position: static;';
    const root = hoverHost.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = HOVER_CSS;
    const card = document.createElement('div');
    card.className = 'card';
    card.setAttribute('role', 'tooltip');
    root.append(style, card);
    document.body.appendChild(hoverHost);
    hoverRefs = { card };

    // BUG FIX: the card floats independently of the <a> (position: fixed,
    // not a DOM child of the anchor), and onHoverOut fires the instant the
    // pointer leaves the anchor - including when it leaves TOWARD the card
    // itself, e.g. to click the SEBI verify link, scroll a long redirect
    // chain, or just read it properly. Without its own enter/leave handling
    // the card had a hard 120ms window to be reached and then vanished out
    // from under the pointer - this is almost certainly "hover isn't
    // working properly". The card now cancels its own hide timer on entry
    // and restarts it on exit, exactly like a real anchor would.
    card.addEventListener('mouseenter', () => {
      clearTimeout(hoverHideTimer);
      clearTimeout(hoverShowTimer);
    });
    card.addEventListener('mouseleave', () => {
      hoverHideTimer = setTimeout(hideHoverCard, HOVER_HIDE_MS);
    });

    return hoverRefs;
  }

  // Does any ancestor of `el` establish a new CSS containing block (via
  // transform/perspective/filter/contain/will-change)? If so, `position:
  // fixed` descendants of it stop being viewport-relative and instead
  // anchor to THAT ancestor - a well-known trap on pages using smooth-scroll
  // libraries (Lenis, GSAP ScrollSmoother, Locomotive Scroll) that apply a
  // transform to <body> or <html>. The card is appended to document.body,
  // so it only matters here when body/html themselves are the offender -
  // but that does happen, and when it does the card renders in the wrong
  // place, gets clipped, or sits off-screen, which reads as "hover doesn't
  // work" even though the listeners fired correctly.
  function findsFixedPositioningTrap() {
    for (const el of [document.documentElement, document.body]) {
      if (!el) continue;
      const cs = getComputedStyle(el);
      if (cs.transform !== 'none' || cs.perspective !== 'none' ||
          (cs.filter && cs.filter !== 'none') ||
          (cs.willChange && /transform|perspective/.test(cs.willChange)) ||
          (cs.contain && /layout|paint|strict|content/.test(cs.contain))) {
        return true;
      }
    }
    return false;
  }

  function positionHoverCard(anchor) {
    if (!hoverRefs) return;
    const r = anchor.getBoundingClientRect();
    const card = hoverRefs.card;
    // If body/html traps `position: fixed`, fall back to `position: absolute`
    // + document-relative coordinates (scrollX/scrollY-adjusted), which is
    // immune to the trap because it is measured, not inherited.
    const trapped = findsFixedPositioningTrap();
    card.style.position = trapped ? 'absolute' : 'fixed';
    const scrollX = trapped ? window.scrollX : 0;
    const scrollY = trapped ? window.scrollY : 0;

    // Measure once, then place. Flip above/below and clamp horizontally so the
    // card is never off-screen - the old tooltip could render past the viewport.
    const cw = card.offsetWidth || 320;
    const chh = card.offsetHeight || 60;
    const vw = window.innerWidth, vh = window.innerHeight;
    let top = r.bottom + 8;
    if (top + chh > vh - 8) top = Math.max(8, r.top - chh - 8);
    let left = r.left;
    if (left + cw > vw - 8) left = Math.max(8, vw - cw - 8);
    card.style.top = `${Math.round(top + scrollY)}px`;
    card.style.left = `${Math.round(left + scrollX)}px`;
  }

  function renderHoverCard(res, pending) {
    const refs = ensureHoverCard();
    const v = HOVER_VERDICTS[res.verdict] || HOVER_VERDICTS.L0_NO_SIGNALS;
    refs.card.style.setProperty('--accent', v.c);
    refs.card.style.setProperty('--accent-wash', v.c + '1f');

    const parts = [];
    parts.push(`<div class="row"><span class="tag">${escapeHtml(v.t)}</span>`
      + `<span class="host">${escapeHtml(res.host || res.url || '')}</span></div>`);

    if (res.summary) parts.push(`<div class="summary">${escapeHtml(res.summary)}</div>`);

    // What was actually checked.
    //
    // "NO SIGNALS" on its own is true and tells the user nothing. A clean result
    // is only worth something if they can see its basis and its limits - which
    // lists, how many entries, refreshed when, and what that does not cover.
    // This block is the difference between a shrug and an answer.
    const rep = res.reputation;
    if (rep && !rep.error) {
      const ev = [];
      if ((rep.listed || []).length) {
        rep.listed.forEach((l) => {
          ev.push(`<div class="sig sev-high"><span class="dot">!</span>`
            + `<span>Listed on ${escapeHtml(l.list)} as ${escapeHtml(l.kind)}`
            + (l.matched && l.matched !== rep.host ? ` (via ${escapeHtml(l.matched)})` : '')
            + `</span></div>`);
        });
      } else if (rep.rbi_namespace || rep.whitelisted) {
        // A licence-gated or explicitly-verified host gets a short green
        // line, not a paragraph of provenance. The user hovering a link is
        // deciding whether to click, and at that moment 'verified' is the
        // whole message.
        ev.push('<div class="sig pol-protective"><span class="dot">\u2713</span>'
          + `<span>${escapeHtml(rep.verified_label || 'Verified official domain')}</span></div>`);
      } else if (rep.coverage_note) {
        ev.push(`<div class="checked">${escapeHtml(rep.coverage_note)}</div>`);
      }

      const intel = rep.intel || {};
      (intel.signals || []).forEach((s) => {
        const cls = PhishermanSignalPolarity.classify(s);
        const dot = cls.polarity === 'protective' ? '✓'
          : cls.severity === 'high' ? '!' : cls.severity === 'medium' ? '~' : 'i';
        ev.push(`<div class="sig ${cls.polarity === 'protective'
          ? 'pol-protective' : 'sev-' + cls.severity}">`
          + `<span class="dot">${dot}</span><span>${escapeHtml(s)}</span></div>`);
      });

      if (intel.https === false) {
        ev.push('<div class="sig sev-medium"><span class="dot">~</span>'
          + '<span>Not encrypted — anything you type here travels in the clear</span></div>');
      }
      if (ev.length) parts.push(`<div class="chain">${ev.join('')}</div>`);
    } else if (rep === undefined && res.verdict === 'L0_NO_SIGNALS') {
      // Backend asleep. Say which check did NOT run rather than implying the
      // clean result covered more than it did.
      parts.push('<div class="checked">Address checked on this device only. '
        + 'Blocklist lookup needs the local backend, which is not running.</div>');
    }

    const d = res.destination;
    if (d) {
      const chain = [];
      if (pending) {
        chain.push('<div class="pending">Checking where this link goes…</div>');
      } else if (d.refused) {
        chain.push(`<div class="muted">${escapeHtml(d.reason || 'Destination not checked.')}</div>`);
      } else if (d.hops && d.hops.length > 1) {
        d.hops.forEach((h, i) => {
          const last = i === d.hops.length - 1;
          chain.push(`<div class="hop${last ? ' final' : ''}">`
            + `<span class="n">${last ? '→' : i + 1 + '.'}</span>`
            + `<span class="h">${escapeHtml(h.host || '')}</span></div>`);
        });
        if (d.truncated) chain.push('<div class="muted">Chain continues further.</div>');
      } else if (d.resolved) {
        chain.push('<div class="muted">No redirect — this link goes where it says.</div>');
      }
      (d.signals || []).forEach((s) => {
        chain.push(`<div class="sig sev-${s.severity || 'none'}">`
          + `<span class="dot">${s.severity === 'high' ? '!' : s.severity === 'medium' ? '~' : 'i'}</span>`
          + `<span>${escapeHtml(s.label)}</span></div>`);
      });
      if (chain.length) parts.push(`<div class="chain">${chain.join('')}</div>`);
    }

    // Real, one-click paths to genuine .gov.in reporting/verification
    // surfaces for verdicts a user would actually act on. These are the
    // same official sources the backend directory tracks in
    // engines/official_gov_verify.py - kept identical here so the hover
    // card and the side panel never point to two different lists.
    const HIGH_RISK = new Set(['L5_KNOWN_BAD', 'L4_IDENTITY_MISMATCH', 'L3_PAYMENT_RISK']);
    if (HIGH_RISK.has(res.verdict)) {
      parts.push(
        '<div class="chain govlinks">' +
        '<a href="https://www.cybercrime.gov.in/" target="_blank" rel="noopener">Report on cybercrime.gov.in ↗</a>' +
        ' · <a href="https://scores.gov.in/" target="_blank" rel="noopener">SEBI SCORES ↗</a>' +
        '</div>'
      );
    }

    refs.card.innerHTML = parts.join('');
  }

  async function showHoverCard(anchor, href) {
    const token = ++hoverToken;
    hoverAnchor = anchor;

    let res;
    try {
      res = await chrome.runtime.sendMessage({
        action: 'preflightLink', url: href, pageHost: window.location.hostname,
      });
    } catch {
      return;                       // worker asleep or extension reloading
    }
    if (token !== hoverToken || !res || res.error) return;

    renderHoverCard(res, res.destination && !res.destination.refused && !res.destination.hops?.length);
    const refs = ensureHoverCard();
    positionHoverCard(anchor);
    requestAnimationFrame(() => refs.card.classList.add('in'));
  }

  function hideHoverCard() {
    clearTimeout(hoverShowTimer);
    clearTimeout(hoverHideTimer);
    hoverToken++;                   // any in-flight response is now stale
    hoverAnchor = null;
    if (!hoverHost) return;
    const host = hoverHost, refs = hoverRefs;
    hoverHost = null; hoverRefs = null;
    if (refs && refs.card) refs.card.classList.remove('in');
    setTimeout(() => host.remove(), 140);
  }

  // --- Message Listeners ---

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'snapshotPage') {
      try {
        const snapshot = buildSnapshot();
        sendResponse(snapshot);
      } catch (err) {
        sendResponse({ error: err.message });
      }
      return false;
    }

    if (message.action === 'renderAssessment') {
      const { assessment, settings } = message;
      window.__phishermanLastAssessment = assessment;
      createOverlay(assessment, settings);
      sendResponse({ ok: true });
      return false;
    }

    if (message.action === 'getSelectionContext') {
      buildSelectionSnapshot(message.selectedText || '')
        .then(snapshot => sendResponse(snapshot || { error: 'No active text selection found' }))
        .catch(err => sendResponse({ error: err.message }));
      return true;
    }

    return false;
  });

  // ─── WhatsApp Web - Live Message Observer ────────────────────────────────
  // MutationObserver watches for new message bubbles arriving in real time.
  // Debounced 1.5s so we batch rapid incoming messages into one scan.

  function installWhatsAppObserver() {
    if (!window.location.hostname.includes('web.whatsapp.com')) return;

    let debounceTimer = null;
    let scannedMessageIds = new Set();

    // WhatsApp Web is a single-page app: switching conversation swaps the
    // contents of #main without a navigation event, so nothing here used to
    // learn that the chat had changed. Two consequences, both bad:
    //
    //   1. `scannedMessageIds` accumulated across every chat in the session.
    //      WhatsApp's data-id values are not globally unique in practice, so
    //      a fresh message in chat B could collide with a seen id from chat A
    //      and be skipped entirely - a scam silently never scanned.
    //   2. The island and the side panel kept displaying the PREVIOUS chat's
    //      verdict against the new conversation. A "no signals" result from a
    //      family thread stayed on screen while a scammer's opening message
    //      sat directly beneath it.
    //
    // (2) is the more dangerous of the two: a stale reassuring verdict is
    // worse than no verdict, because the user has been given a reason to
    // relax that was computed about somebody else's messages.
    let currentChatKey = null;

    function chatKey() {
      // Prefer the header title node; fall back to the main pane's own id.
      const header = document.querySelector('#main header');
      const title = header
        ? (header.querySelector('[title]')?.getAttribute('title')
           || header.innerText?.split('\n')[0] || '').trim()
        : '';
      const anyBubble = document.querySelector('#main [data-id]');
      const idHint = anyBubble?.getAttribute('data-id')?.split('_')?.[1] || '';
      return `${title}|${idHint}`;
    }

    function resetForNewChat(key) {
      currentChatKey = key;
      scannedMessageIds = new Set();
      // Pull down anything on screen that was computed about the old chat.
      try { removeOverlay(); } catch (e) { /* island may not exist */ }
      // Tell the panel to drop its cached assessment rather than keep
      // rendering it beside a different conversation.
      try {
        chrome.runtime.sendMessage({
          action: 'chatContextChanged',
          url: window.location.href,
          chatTitle: key.split('|')[0] || '',
        });
      } catch (e) { /* worker asleep; the local reset above still happened */ }
    }

    const observer = new MutationObserver(() => {
      // Check for a chat switch on every mutation, BEFORE the debounce -
      // debouncing this would leave the stale verdict up for the full
      // 1.5s window, which is exactly the moment the user is reading the
      // new chat's first message.
      const key = chatKey();
      if (key !== currentChatKey && key !== '|') {
        resetForNewChat(key);
      }

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const waData = extractWhatsAppMessages();
        if (!waData?.records?.length) return;

        // Namespace seen-ids by chat, so a collision across conversations
        // cannot suppress a scan.
        const freshRecords = waData.records.filter(
          record => !scannedMessageIds.has(`${currentChatKey}::${record.id}`));
        if (freshRecords.length === 0) return;
        freshRecords.forEach(
          record => scannedMessageIds.add(`${currentChatKey}::${record.id}`));

        const flaggedRecords = freshRecords
          .map(record => {
            const localResult = window.__phishermanLocalGate
              ? window.__phishermanLocalGate(record.text, record)
              : null;
            return localResult && localResult.signals.length > 0
              ? { ...record, localResult }
              : null;
          })
          .filter(Boolean);

        if (flaggedRecords.length === 0) return;

        flaggedRecords.forEach(record => flagWhatsAppBubble(record.id, record.localResult));

        const combinedText = flaggedRecords.map(record => record.text).join('\n\n');
        const localSummary = mergeLocalWhatsAppAssessments(flaggedRecords);
        showWhatsAppWarningV2(localSummary);

        chrome.runtime.sendMessage({
          action: 'scanText',
          text: combinedText,
          url: window.location.href,
          source: 'whatsapp-web',
          title: `${waData.chatTitle} · WhatsApp message scan`,
          chatTitle: waData.chatTitle,
          messageCount: flaggedRecords.length,
          flaggedMessages: flaggedRecords.map(record => ({
            id: record.id,
            text: summarizeMessage(record.text, 220),
            signals: record.localResult.signals,
            category: record.localResult.category,
            trustScore: record.localResult.trustScore,
          })),
        });
      }, 1500);
    });

    // Watch the message list container
    const tryObserve = () => {
      const pane = document.querySelector('#main') || document.querySelector('[data-tab="8"]');
      if (pane) {
        observer.observe(pane, { childList: true, subtree: true });
      } else {
        setTimeout(tryObserve, 2000); // WhatsApp loads lazily
      }
    };
    tryObserve();
  }

  function flagWhatsAppBubble(messageId, result) {
    if (!window.CSS?.escape) return;
    const bubble = document.querySelector(`[data-id="${CSS.escape(messageId)}"]`);
    if (!bubble || bubble.querySelector('.phisherman-wa-inline-flag')) return;

    bubble.style.outline = '2px solid rgba(239, 68, 68, 0.85)';
    bubble.style.outlineOffset = '2px';
    bubble.style.borderRadius = '12px';

    const flag = document.createElement('div');
    flag.className = 'phisherman-wa-inline-flag';
    flag.style.cssText = `
      margin-top: 6px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(127, 29, 29, 0.92);
      color: #fecaca;
      font-size: 11px;
      font-family: system-ui, sans-serif;
      font-weight: 700;
      letter-spacing: 0.02em;
    `;
    flag.textContent = `FLAGGED: ${result.category || 'Scam message'}`;
    bubble.appendChild(flag);
  }

  function mergeLocalWhatsAppAssessments(flaggedRecords) {
    const worstScore = Math.min(...flaggedRecords.map(record => record.localResult.trustScore));
    const dedupedSignals = [...new Set(flaggedRecords.flatMap(record => record.localResult.signals))];
    const categories = [...new Set(flaggedRecords.map(record => record.localResult.category).filter(Boolean))];
    return {
      trustScore: worstScore,
      riskLevel: worstScore <= 24 ? 'DANGER' : worstScore <= 49 ? 'WARNING' : 'CAUTION',
      category: categories[0] || 'Scam/phishing',
      signals: dedupedSignals.map(signal => normalizeSignal(signal)),
      flaggedMessages: flaggedRecords.map(record => ({
        summary: summarizeMessage(record.text),
        signals: record.localResult.signals,
      })),
    };
  }

  function showWhatsAppWarning(result) {
    const existing = document.getElementById('phisherman-wa-warning');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'phisherman-wa-warning';
    banner.style.cssText = `
      position: fixed; top: 60px; right: 12px; z-index: 9999;
      background: #1a1a2e; border: 1px solid #ef4444; border-radius: 10px;
      padding: 10px 14px; max-width: 280px; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
      font-family: system-ui, sans-serif; font-size: 12px; color: #e2e8f0;
    `;
    const topSignals = result.signals.slice(0, 2).join(' · ');
    banner.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:16px;">🛡️</span>
        <strong style="color:#ef4444;font-size:13px;">Phisherman AI: Scam Risk Detected</strong>
        <button id="phisherman-wa-dismiss" style="margin-left:auto;background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;">✕</button>
      </div>
      <div style="color:#94a3b8;line-height:1.5;">${topSignals}</div>
      <div style="margin-top:6px;color:#f97316;font-size:11px;">Do not share OTP, UPI PIN, or personal details.</div>
    `;

    document.body.appendChild(banner);
    document.getElementById('phisherman-wa-dismiss')?.addEventListener('click', () => banner.remove());
    setTimeout(() => banner?.remove(), 15000);
  }

  // Expose local gate to content script context for WA observer
  // (simplified - just keyword check for instant response)
  window.__phishermanLocalGate = (text) => {
    const signals = [];
    const t = text.toLowerCase();
    if (/upi.{0,20}collect|kyc.{0,20}expir|aadhaar.{0,20}updat/.test(t)) signals.push('UPI/KYC urgency');
    if (/digital.{0,10}arrest|cbi.{0,20}notice|arrest.{0,10}warrant/.test(t)) signals.push('Digital arrest scam');
    if (/(?:share|send|give).{0,20}otp|one.time.pass/.test(t)) signals.push('OTP solicitation');
    if (/guaranteed.{0,15}return|daily.{0,10}profit|task.{0,15}earn/.test(t)) signals.push('Investment/task scam');
    if (/kbc.{0,20}(?:winner|prize)|congratulation.{0,20}won/.test(t)) signals.push('Lottery scam');
    if (/(?:bit\.ly|tinyurl).*(?:bank|kyc|upi|pay|urgent)/.test(t)) signals.push('Suspicious link');
    return { signals, trustScore: signals.length > 0 ? Math.max(20, 72 - signals.length * 20) : 80 };
  };

  function showWhatsAppWarningV2(result) {
    const existing = document.getElementById('phisherman-wa-warning');
    if (existing) existing.remove();

    const score = Math.round(result.trustScore ?? 30);
    const riskLabel = result.riskLevel || (score <= 24 ? 'DANGER' : score <= 49 ? 'WARNING' : 'CAUTION');
    const topSignals = (result.signals || []).slice(0, 3).map(signal => signal.label || signal).join(' · ');
    const evidence = result.flaggedMessages?.[0]?.summary || '';

    const banner = document.createElement('div');
    banner.id = 'phisherman-wa-warning';
    banner.style.cssText = `
      position: fixed; top: 72px; right: 12px; z-index: 9999;
      background: linear-gradient(180deg, #111827, #0f172a);
      border: 1px solid #ef4444; border-radius: 14px;
      padding: 12px 14px; max-width: 340px; box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      font-family: system-ui, sans-serif; font-size: 12px; color: #e2e8f0;
    `;
    banner.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
        <div style="
          width: 40px; height: 40px; border-radius: 50%;
          display:flex; align-items:center; justify-content:center;
          border: 3px solid #ef4444; color: #ef4444; font-weight: 800; font-size: 16px;
          flex-shrink: 0;
        ">${score}</div>
        <div>
          <div style="color:#fecaca;font-size:13px;font-weight:800;letter-spacing:0.04em;">MESSAGE FLAGGED</div>
          <div style="color:#fca5a5;font-size:12px;">${escapeHtml(result.category || 'Potential scam or phishing')}</div>
        </div>
        <button id="phisherman-wa-dismiss" style="margin-left:auto;background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;">×</button>
      </div>
      <div style="display:inline-block;padding:2px 8px;border-radius:999px;background:#7f1d1d;color:#fecaca;font-size:10px;font-weight:700;margin-bottom:8px;">${riskLabel}</div>
      <div style="color:#cbd5e1;line-height:1.45;">${escapeHtml(topSignals || 'Suspicious social-engineering signals detected in the latest WhatsApp message.')}</div>
      ${evidence ? `<div style="margin-top:8px;padding:8px 10px;border-radius:10px;background:#111827;border:1px solid #1f2937;color:#94a3b8;line-height:1.45;">"${escapeHtml(evidence)}"</div>` : ''}
      <div style="margin-top:8px;color:#fca5a5;font-size:11px;">Direct flagging is on. Avoid clicking links or sending OTP, UPI PIN, Aadhaar, bank details, or advance payments.</div>
    `;

    document.body.appendChild(banner);
    document.getElementById('phisherman-wa-dismiss')?.addEventListener('click', () => banner.remove());
    setTimeout(() => banner?.remove(), 18000);
  }

  window.__phishermanLocalGate = (text, record = null) => {
    const signals = [];
    const t = text.toLowerCase();
    let category = '';

    if (/upi.{0,20}collect|kyc.{0,20}expir|aadhaar.{0,20}updat|bank.{0,20}freeze|account.{0,20}suspend/.test(t)) {
      signals.push('Urgent KYC, bank, or payment verification request');
      category = category || 'Credential or payment phishing';
    }
    if (/digital.{0,10}arrest|cbi.{0,20}notice|arrest.{0,10}warrant|police.{0,20}video|customs.{0,20}seize/.test(t)) {
      signals.push('Authority impersonation or digital arrest pressure');
      category = category || 'Authority impersonation scam';
    }
    if (/(?:share|send|give|enter).{0,20}otp|one.time.pass|verification.{0,10}code/.test(t)) {
      signals.push('OTP or verification code solicitation');
      category = category || 'Account takeover phishing';
    }
    if (/guaranteed.{0,20}profit|daily.{0,12}profit|task.{0,20}earn|earn.{0,20}commission|send me 10%|investment group|trading group/.test(t)) {
      signals.push('Task, commission, or guaranteed-profit bait');
      category = category || 'Investment or task scam';
    }

    // Rating / part-time-job recruitment.
    //
    // This is the most common WhatsApp scam pattern in India and the block
    // above missed it completely. A real message reading "give positive
    // ratings to the brands we work with... you can earn 1500 to 5000 rupees
    // per day... payments are made daily via UPI... 150 rupees joining bonus
    // ... reply YES" triggers NOTHING above: the word "task" never appears,
    // and "daily" is adjacent to "via UPI" rather than to "profit".
    //
    // The lesson is that the patterns above are keyed to the scam's
    // vocabulary rather than its STRUCTURE. The structure is stable even
    // when the wording rotates: an unsolicited offer of per-day income for
    // trivial work, paid through a consumer rail, with a small up-front
    // sweetener and a one-word reply as the hook. Each clause below matches
    // one limb of that structure.
    const ratingBait = [
      // Per-day / per-task income promise with a rupee figure.
      /(?:earn|make|get|paid?)\s*(?:up\s*to\s*)?(?:rs\.?|₹|inr)?\s*\d{3,6}(?:\s*(?:-|to|–)\s*(?:rs\.?|₹)?\s*\d{3,6})?\s*(?:rupees?\s*)?(?:per|a|each|\/)\s*(?:day|task|job|review|rating|order)/,
      // The work itself: rating/liking/reviewing for pay.
      /(?:positive\s+)?(?:rating|review|like|subscrib|follow)\w*\s+(?:the\s+)?(?:brand|product|video|channel|hotel|app|listing)/,
      // Recruitment framing for "simple" remote work.
      /(?:part[\s-]?time|remote|online|home)\s*(?:work|job|earning)|work\s+is\s+very\s+simple|simple\s+(?:task|work|job)/,
      // Joining bonus / advance sweetener.
      /(?:joining|welcome|signup|sign[\s-]?up)\s*bonus|bonus\s+after\s+(?:completing|a\s+quick)/,
      // Reply-with-a-keyword hook.
      /reply\s+(?:with\s+)?["']?(?:yes|interested|ok|start|join)["']?/,
    ];
    const ratingHits = ratingBait.filter((re) => re.test(t)).length;
    // Two limbs, not one. "Remote work" alone is an ordinary phrase and
    // firing on it would flag every genuine job message on the platform -
    // a false positive here trains the user to dismiss the island, which
    // costs more than the miss it prevents.
    if (ratingHits >= 2) {
      signals.push('Unsolicited paid-rating or part-time-job recruitment, a '
        + 'common advance-fee pattern: the "salary" arrives only after you '
        + 'have deposited your own money');
      category = category || 'Task or rating job scam';
    }

    // Payment rail named to a stranger in an income pitch. Not adverse by
    // itself - UPI is how India pays for everything - but in combination
    // with the recruitment structure above it is the mechanism by which the
    // loss actually occurs, and naming it helps the user see the shape.
    if (ratingHits >= 2 && /\bupi\b|bank\s+account|paytm|phonepe|gpay|google\s*pay/.test(t)) {
      signals.push('Payment rail named by someone you have not met, alongside an income offer');
    }
    if (/kbc.{0,20}(?:winner|prize)|congratulation.{0,20}won|lottery|lucky draw/.test(t)) {
      signals.push('Prize, lottery, or winnings claim');
      category = category || 'Prize scam';
    }
    if (/(?:bit\.ly|tinyurl|cutt\.ly|rb\.gy|is\.gd)|(?:www\.)?[a-z0-9-]+\.(?:xyz|top|click|loan|cfd|sbs|shop)\b/.test(t)) {
      signals.push('Shortened or high-risk link pattern');
      category = category || 'Link-based phishing';
    }
    if (record?.isForwarded) {
      signals.push('Forwarded message social-spread pattern');
    }

    return {
      signals,
      category,
      trustScore: signals.length > 0 ? Math.max(8, 78 - signals.length * 18) : 84,
    };
  };

  // --- Init ---

  chrome.storage?.local?.get('phisherman_settings', (result) => {
    const s = result?.phisherman_settings || {};
    if (s.submitGuard !== false) installSubmitGuard();
    if (s.linkHoverTooltips !== false) installLinkHoverTooltips();
    installWhatsAppObserver(); // always on for WhatsApp Web
  });

  let selectionScanTimer = null;
  let lastSelectionFingerprint = '';

  function scheduleSelectionAnalysis() {
    clearTimeout(selectionScanTimer);
    selectionScanTimer = setTimeout(async () => {
      const selectedText = normalizeText(window.getSelection?.()?.toString() || '');
      if (selectedText.length < 20) return;

      const fingerprint = `${window.location.href}::${selectedText.slice(0, 280)}`;
      if (fingerprint === lastSelectionFingerprint) return;
      lastSelectionFingerprint = fingerprint;

      try {
        const snapshot = await buildSelectionSnapshot(selectedText);
        if (!snapshot) return;
        await chrome.runtime.sendMessage({
          action: 'scanSelectionContext',
          payload: snapshot,
        });
      } catch {}
    }, 700);
  }

  document.addEventListener('mouseup', scheduleSelectionAnalysis, true);
  document.addEventListener('keyup', (event) => {
    if (event.key === 'Shift' || event.key.startsWith('Arrow')) {
      scheduleSelectionAnalysis();
    }
  }, true);

})();
