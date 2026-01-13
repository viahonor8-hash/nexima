(() => {
  const config = {
    // TODO: подключить CRM (Bitrix24/Amo/HubSpot) вместо endpoint-заглушки.
    apiEndpoint: "/api/lead",
    basePackages: {
      entry: { label: "Entry", price: 1 },
      localization: { label: "Localization", price: 2 },
      launch: { label: "Launch", price: 3 },
      retainer: { label: "Retainer", price: 4 },
      scale: { label: "Scale", price: 5 }
    },
    coefficients: {
      sku: {
        "1-3": 1.0,
        "4-8": 1.2,
        "9-15": 1.5,
        "16+": 1.8
      },
      platforms: {
        "1": 1.0,
        "2": 1.35,
        "3": 1.7
      },
      speed: {
        standard: 1.0,
        fast: 1.25,
        urgent: 1.5
      },
      sla: {
        "48h": 1.0,
        "24h": 1.2
      },
      risk: {
        low: 1.0,
        mid: 1.15,
        high: 1.35
      }
    }
  };

  const qs = (selector, scope = document) => scope.querySelector(selector);
  const qsa = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  const analytics = {
    send(eventName, params = {}) {
      if (window.gtag) {
        window.gtag("event", eventName, params);
      }
      if (window.ym) {
        window.ym(12345678, "reachGoal", eventName, params);
      }
    }
  };

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const setYear = () => {
    const yearEl = qs("#year");
    if (yearEl) {
      yearEl.textContent = String(new Date().getFullYear());
    }
  };

  const setupNav = () => {
    const toggle = qs(".nav__toggle");
    const menu = qs(".nav__menu");
    if (!toggle || !menu) return;

    const updateMenuVisibility = () => {
      const isMobile = window.matchMedia("(max-width: 767px)").matches;
      if (!isMobile) {
        menu.classList.remove("is-open");
        menu.setAttribute("aria-hidden", "false");
        toggle.setAttribute("aria-expanded", "false");
      } else {
        menu.setAttribute("aria-hidden", "true");
      }
    };

    updateMenuVisibility();
    window.addEventListener("resize", updateMenuVisibility, { passive: true });

    toggle.addEventListener("click", () => {
      const isOpen = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
      menu.setAttribute("aria-hidden", String(!isOpen));
    });

    qsa(".nav__links a").forEach((link) => {
      link.addEventListener("click", () => {
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        menu.setAttribute("aria-hidden", "true");
      });
    });
  };

  const setupAnchorTracking = () => {
    qsa('[data-analytics="anchor"]').forEach((link) => {
      link.addEventListener("click", () => {
        analytics.send("anchor_click", { label: link.getAttribute("href") });
      });
    });
  };

  const setupSmoothAnchors = () => {
    const header = qs("#header");
    qsa('a[href^="#"]').forEach((link) => {
      link.addEventListener("click", (event) => {
        const targetId = link.getAttribute("href");
        if (!targetId || targetId === "#") return;
        const target = qs(targetId);
        if (!target) return;

        event.preventDefault();
        const headerOffset = header ? header.offsetHeight + 12 : 0;
        const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - headerOffset;
        window.scrollTo({ top: targetPosition, behavior: prefersReducedMotion ? "auto" : "smooth" });
      });
    });
  };

  const setupTabs = () => {
    const tabs = qs("[data-tabs]");
    if (!tabs) return;

    const tabButtons = qsa(".tabs__tab", tabs);
    const panels = qsa(".tabs__panel", tabs);

    tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        tabButtons.forEach((btn) => {
          btn.classList.remove("is-active");
          btn.setAttribute("aria-selected", "false");
        });
        panels.forEach((panel) => panel.classList.remove("is-active"));

        const target = button.dataset.tab;
        const panel = qs(`#${target}`);
        if (panel) {
          panel.classList.add("is-active");
          button.classList.add("is-active");
          button.setAttribute("aria-selected", "true");
          analytics.send("tab_switch", { tab: target });
        }
      });
    });
  };

  const setupAccordion = () => {
    const items = qsa(".faq__item");
    items.forEach((item) => {
      const button = qs(".faq__question", item);
      const answer = qs(".faq__answer", item);
      if (!button || !answer) return;

      button.addEventListener("click", () => {
        const isOpen = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!isOpen));
        answer.hidden = isOpen;
      });
    });
  };

  const formatNumber = (value) => new Intl.NumberFormat("ru-RU").format(value);

  const updateCalculatorOptions = () => {
    const packageSelect = qs("#calc-package");
    if (!packageSelect) return;

    packageSelect.innerHTML = Object.entries(config.basePackages)
      .map(
        ([key, value]) =>
          `<option value="${key}">${value.label} — ${value.price}</option>`
      )
      .join("");
  };

  const calculatePrice = (values) => {
    const base = config.basePackages[values.package]?.price ?? 0;
    const multiplier =
      config.coefficients.sku[values.sku] *
      config.coefficients.platforms[values.platforms] *
      config.coefficients.speed[values.speed] *
      config.coefficients.sla[values.sla] *
      config.coefficients.risk[values.risk];
    return { base, multiplier, total: base * multiplier };
  };

  const updateCalculatorResult = () => {
    const form = qs("#calculatorForm");
    if (!form) return;

    const values = Object.fromEntries(new FormData(form).entries());
    const result = calculatePrice(values);
    const priceEl = qs("#calc-price");
    const breakdown = qs("#calc-breakdown");

    if (priceEl) {
      priceEl.textContent = result.total ? formatNumber(Number(result.total.toFixed(2))) : "—";
    }

    if (breakdown) {
      breakdown.innerHTML = `
        <div>База: ${formatNumber(result.base)}</div>
        <div>KSKU: ${config.coefficients.sku[values.sku]}</div>
        <div>KPLAT: ${config.coefficients.platforms[values.platforms]}</div>
        <div>KSPEED: ${config.coefficients.speed[values.speed]}</div>
        <div>KSLA: ${config.coefficients.sla[values.sla]}</div>
        <div>KRISK: ${config.coefficients.risk[values.risk]}</div>
      `;
    }
  };

  const setupCalculator = () => {
    const form = qs("#calculatorForm");
    if (!form) return;

    updateCalculatorOptions();
    updateCalculatorResult();

    form.addEventListener("change", () => {
      updateCalculatorResult();
      analytics.send("calculator_change", { source: "calculator" });
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      updateCalculatorResult();
      analytics.send("calculator_submit", { source: "calculator" });

      const longForm = qs("#longForm");
      if (longForm) {
        const commentField = qs('textarea[name="comment"]', longForm);
        const values = Object.fromEntries(new FormData(form).entries());
        if (commentField) {
          commentField.value = `Запрос по калькулятору: пакет ${values.package}, SKU ${values.sku}, платформы ${values.platforms}, скорость ${values.speed}, SLA ${values.sla}, риски ${values.risk}.`;
        }
        longForm.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  };

  const getUtmParams = () => {
    const params = new URLSearchParams(window.location.search);
    const utmKeys = [
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content"
    ];
    return utmKeys.reduce((acc, key) => {
      if (params.get(key)) {
        acc[key] = params.get(key);
      }
      return acc;
    }, {});
  };

  const populateUtmFields = (utm) => {
    qsa("[data-utm-fields]").forEach((container) => {
      container.innerHTML = Object.entries(utm)
        .map(([key, value]) => `<input type="hidden" name="${key}" value="${value}" />`)
        .join("");
    });
  };

  const serializeForm = (form) => {
    const data = new FormData(form);
    const payload = {};
    data.forEach((value, key) => {
      if (payload[key]) {
        payload[key] = [].concat(payload[key], value);
      } else {
        payload[key] = value;
      }
    });
    return payload;
  };

  const saveDraft = (formId, payload) => {
    localStorage.setItem(`draft_${formId}`, JSON.stringify(payload));
  };

  const clearDraft = (formId) => {
    localStorage.removeItem(`draft_${formId}`);
  };

  const setupFormSubmission = (form) => {
    const status = qs(".form__status", form);
    const formId = form.getAttribute("id");

    const showStatus = (message, type = "info") => {
      if (!status) return;
      status.textContent = message;
      status.dataset.state = type;
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const honeypot = qs('input[name="website"]', form);
      if (honeypot && honeypot.value) {
        showStatus("Ошибка отправки. Попробуйте позже.", "error");
        analytics.send("form_error", { form: formId, reason: "bot" });
        return;
      }

      const payload = serializeForm(form);
      analytics.send("form_submit", { form: formId });
      showStatus("Отправляем...", "info");

      try {
        const response = await fetch(config.apiEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...payload,
            form: formId,
            url: window.location.href
          })
        });

        if (!response.ok) {
          throw new Error("network");
        }

        showStatus("Заявка принята. Мы свяжемся и уточним входные данные.", "success");
        analytics.send("form_success", { form: formId });
        clearDraft(formId);
        form.reset();
      } catch (error) {
        saveDraft(formId, payload);
        showStatus("Ошибка сети. Сохранено как черновик — можно повторить отправку.", "error");
        analytics.send("form_error", { form: formId, reason: "network" });
        addRetryButton(form, payload);
      }
    });
  };

  const addRetryButton = (form, payload) => {
    if (qs(".form__retry", form)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn--ghost form__retry";
    button.textContent = "Повторить отправку";
    button.addEventListener("click", async () => {
      try {
        await fetch(config.apiEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const status = qs(".form__status", form);
        if (status) {
          status.textContent = "Заявка принята. Мы свяжемся и уточним входные данные.";
        }
        analytics.send("form_success", { form: form.getAttribute("id"), retry: true });
        button.remove();
      } catch (error) {
        analytics.send("form_error", { form: form.getAttribute("id"), retry: true });
      }
    });
    form.appendChild(button);
  };

  const setupForms = () => {
    qsa("form.form").forEach((form) => setupFormSubmission(form));
  };

  const setupCtaTracking = () => {
    qsa('[data-analytics="cta"]').forEach((cta) => {
      cta.addEventListener("click", () => {
        analytics.send("cta_click", {
          label: cta.textContent.trim(),
          location: cta.dataset.ctaLocation || "unknown"
        });
      });
    });
  };

  const init = () => {
    setYear();
    setupNav();
    setupAnchorTracking();
    setupSmoothAnchors();
    setupTabs();
    setupAccordion();
    setupCalculator();
    setupForms();
    setupCtaTracking();

    const utm = getUtmParams();
    populateUtmFields(utm);
  };

  init();
})();
