/* Shared NOC primitives. Business templates use ui-* interfaces backed by Naive UI. */
const NocUI = (() => {
  const { h, defineComponent } = Vue;
  const styles = getComputedStyle(document.documentElement);
  const token = name => styles.getPropertyValue(`--${name}`).trim();
  const themeOverrides = {
    common: {
      primaryColor: token('brand'), primaryColorHover: token('brand-hover'),
      primaryColorPressed: token('brand-pressed'), primaryColorSuppl: token('brand'),
      borderRadius: '6px', textColorBase: token('ink'),
      textColor1: token('ink'), textColor2: token('text-secondary'), textColor3: token('muted'),
      placeholderColor: token('placeholder'), borderColor: token('line'), dividerColor: token('divider'),
      bodyColor: token('bg'), cardColor: token('panel'), modalColor: token('panel'),
      popoverColor: token('panel'), tableColor: token('panel'), inputColor: token('panel'),
      successColor: token('success'), successColorHover: token('success'), successColorPressed: token('success'),
      errorColor: token('danger'), errorColorHover: token('danger'), errorColorPressed: token('danger'),
      warningColor: token('warning-ink'), warningColorHover: token('warning-ink'), warningColorPressed: token('warning-ink'),
      infoColor: token('brand'), infoColorHover: token('brand-hover'), infoColorPressed: token('brand-pressed'),
      fontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
    },
    DataTable: {
      thColor: token('panel-muted'), tdColorStriped: token('panel'), tdColorHover: token('bg-rail'),
      borderColor: token('divider'), thTextColor: token('muted'),
    },
    Card: { borderRadius: token('surface-radius'), titleFontSizeMedium: '16px' },
    Dialog: { borderRadius: token('surface-radius'), titleFontSize: '17px' },
    Button: {
      paddingSmall: '0 16px', paddingMedium: '0 22px', paddingLarge: '0 26px',
    },
    Tag: {
      borderRadius: '4px',
      color: token('tag-neutral-bg'), textColor: token('tag-neutral-ink'),
      colorPrimary: token('tag-info-bg'), textColorPrimary: token('tag-info-ink'),
      colorInfo: token('tag-neutral-bg'), textColorInfo: token('tag-neutral-ink'),
      colorSuccess: token('tag-success-bg'), textColorSuccess: token('tag-success-ink'),
      colorWarning: token('tag-warning-bg'), textColorWarning: token('tag-warning-ink'),
      colorError: token('tag-danger-bg'), textColorError: token('tag-danger-ink'),
    },
    Menu: {
      borderRadius: '8px',
      itemColorHover: token('nav-hover'), itemColorActive: token('nav-active'), itemColorActiveHover: token('nav-active'),
      itemColorActiveCollapsed: token('nav-active'),
      itemTextColor: token('nav-text'), itemTextColorHover: token('nav-text-active'),
      itemTextColorActive: token('nav-text-active'), itemTextColorActiveHover: token('nav-text-active'),
      itemIconColor: token('nav-text'), itemIconColorHover: token('nav-text-active'),
      itemIconColorCollapsed: token('nav-text'),
      itemIconColorActive: token('nav-text-active'), itemIconColorActiveHover: token('nav-text-active'),
    },
  };
  const services = naive.createDiscreteApi(['message', 'dialog'], {
    configProviderProps: { themeOverrides },
  });
  const message = {};
  ['success', 'error', 'warning', 'info'].forEach(kind => {
    message[kind] = value => services.message[kind](typeof value === 'string' ? value : value.message);
  });
  const dialog = {
    confirm(content, title, options = {}) {
      return new Promise((resolve, reject) => {
        let settled = false;
        const cancel = () => {
          if (!settled) { settled = true; reject('cancel'); }
        };
        services.dialog.warning({
          title,
          content: () => h('div', { style: 'white-space:pre-line;overflow-wrap:anywhere' }, content),
          positiveText: options.confirmButtonText || '确认',
          negativeText: options.cancelButtonText || '取消',
          class: options.customClass, maskClosable: false,
          positiveButtonProps: { type: options.confirmButtonClass?.includes('danger') ? 'error' : 'primary' },
          onPositiveClick: () => { settled = true; resolve('confirm'); },
          onNegativeClick: cancel, onClose: cancel, onEsc: cancel,
        });
      });
    },
  };
  dialog.prompt = (content, title, options = {}) => new Promise((resolve, reject) => {
    const value = Vue.ref('');
    const invalid = Vue.ref(false);
    const cancel = () => reject('cancel');
    services.dialog.warning({
      title, maskClosable: false,
      positiveText: options.confirmButtonText || '确认', negativeText: options.cancelButtonText || '取消',
      content: () => h('div', {}, [
        h('p', {}, content),
        h(naive.NInput, {type: 'textarea', value: value.value, maxlength: 2000,
          placeholder: options.inputPlaceholder, 'aria-label': options.inputPlaceholder,
          status: invalid.value ? 'error' : undefined,
          'onUpdate:value': text => { value.value = text; invalid.value = false; }}),
        invalid.value ? h('p', {role: 'alert'}, options.validationMessage) : null,
      ]),
      onPositiveClick: () => {
        if (!value.value.trim()) { invalid.value = true; return false; }
        resolve(value.value.trim());
      },
      onNegativeClick: cancel, onClose: cancel, onEsc: cancel,
    });
  });
  function primitive(tag, baseClass, style, name) {
    return defineComponent({
      name, inheritAttrs: false,
      setup(_, { attrs, slots }) {
        return () => h(tag, {
          ...attrs, class: [baseClass, attrs.class], style: [style, attrs.style],
        }, slots.default?.());
      },
    });
  }
  const tagType = value => ({ danger: 'error', info: 'info', primary: 'primary',
    warning: 'warning', success: 'success' }[value] || 'default');
  function install(app) {
    app.component('ui-config-provider', defineComponent({
      props: ['locale'],
      setup(p, { slots }) {
        return () => h(naive.NConfigProvider, {
          locale: p.locale,
          dateLocale: i18n.global.locale.value === 'en' ? naive.dateEnUS :
            i18n.global.locale.value === 'zh-HK' ? naive.dateZhTW : naive.dateZhCN,
          themeOverrides,
        }, slots);
      },
    }));
    app.component('ui-container', primitive('div', 'noc-container', 'display:flex;min-width:0;min-height:0;flex:1'));
    app.component('ui-main', primitive('main', 'noc-main', 'flex:1;min-width:0;min-height:0'));
    app.component('ui-header', defineComponent({
      inheritAttrs: false, props: ['height'],
      setup(p, { attrs, slots }) {
        return () => h('header', { ...attrs, style: [{ height: p.height, flexShrink: 0 }, attrs.style] }, slots.default?.());
      },
    }));
    app.component('ui-aside', defineComponent({
      inheritAttrs: false, props: ['width'],
      setup(p, { attrs, slots }) {
        return () => h('aside', { ...attrs, style: [{ width: p.width, flexShrink: 0 }, attrs.style] }, slots.default?.());
      },
    }));
    app.component('ui-icon', primitive('span', 'noc-icon',
      'display:inline-flex;align-items:center;justify-content:center;width:1em;height:1em;flex-shrink:0', 'UiIcon'));
    app.component('ui-card', defineComponent({
      inheritAttrs: false, props: ['shadow'],
      setup(_, { attrs, slots }) {
        return () => h(naive.NCard, { ...attrs, contentStyle: 'padding:20px', headerStyle: 'padding:18px 20px' }, slots);
      },
    }));
    app.component('ui-tag', defineComponent({
      inheritAttrs: false, props: ['type', 'effect', 'size'],
      setup(p, { attrs, slots }) {
        return () => h(naive.NTag, { ...attrs, type: tagType(p.type), size: p.size === 'small' ? 'small' : 'medium', bordered: false }, slots);
      },
    }));
    app.component('ui-alert', defineComponent({
      inheritAttrs: false, props: ['type', 'title', 'closable', 'showIcon'],
      setup(p, { attrs, slots }) {
        return () => h(naive.NAlert, { ...attrs, type: p.type || 'info', title: p.title, closable: p.closable === true, showIcon: true }, slots);
      },
    }));
    app.component('ui-menu-item', defineComponent({ props: ['index'], setup: () => () => null }));
    app.component('ui-menu', defineComponent({
      inheritAttrs: false, props: ['defaultActive', 'collapse', 'collapseTransition'], emits: ['select'],
      setup(p, { attrs, slots, emit }) {
        const flatten = nodes => (nodes || []).flatMap(node => node.type === Vue.Fragment ? flatten(node.children) : [node]);
        return () => h(naive.NMenu, {
          ...attrs, value: p.defaultActive, collapsed: !!p.collapse,
          collapsedWidth: 52, collapsedIconSize: 20, indent: 14,
          options: flatten(slots.default?.()).filter(node => node.props?.index).map(node => {
            const children = node.children.default?.() || [];
            return {
              key: node.props.index,
              label: () => h('span', { title: node.props.title || undefined },
                children.filter(child => child.type?.name !== 'UiIcon')),
              icon: () => children.filter(child => child.type?.name === 'UiIcon'),
            };
          }),
          'onUpdate:value': key => emit('select', key),
        });
      },
    }));
    const updateLoading = (el, binding) => {
      el.classList.toggle('noc-loading', !!binding.value);
      el.setAttribute('aria-busy', String(!!binding.value));
    };
    app.directive('loading', { mounted: updateLoading, updated: updateLoading });
    registerNocControls(app);
    registerNocDisplay(app);
  }
  return { message, dialog, install };
})();
