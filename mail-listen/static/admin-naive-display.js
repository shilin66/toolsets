/* Naive UI adapters for the NOC's declarative business templates. */
(function () {
  'use strict';
  window.registerNocDisplay = function (app) {
    const { h, Fragment, Comment, defineComponent, ref, watch, mergeProps, cloneVNode } = Vue;
    const N = naive;
    const size = value => value === 'default' ? 'medium' : value;
    const dimension = value => value == null ? undefined : /^\d+$/.test(String(value)) ? Number(value) : value;
    const flatten = nodes => (nodes || []).flatMap(node => {
      if (!node || node.type === Comment) return [];
      if (node.type === Fragment || Array.isArray(node)) return flatten(Array.isArray(node) ? node : node.children);
      return [node];
    });
    const get = (props, key) => props[key] ?? props[key.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())];
    const marker = name => defineComponent({ name, setup: () => () => null });
    app.component('ui-table-column', marker('NocTableColumn'));
    app.component('ui-table', defineComponent({
      inheritAttrs: false,
      props: {
        data: { type: Array, default: () => [] }, rowKey: [String, Function], stripe: Boolean,
        border: Boolean, size: String, height: [String, Number], maxHeight: [String, Number],
        emptyText: String, rowClassName: [String, Function], expandRowKeys: Array
      },
      emits: ['row-click', 'expand-change'],
      setup(p, { attrs, slots, emit }) {
        const expanded = ref([]);
        const keyFor = row => typeof p.rowKey === 'function' ? p.rowKey(row) : p.rowKey ? row[p.rowKey] : row.id ?? row.email_id ?? p.data.indexOf(row);
        return () => {
          const columns = flatten(slots.default?.()).filter(node => node.type?.name === 'NocTableColumn').map((node, index) => {
            const c = node.props || {};
            const render = node.children?.default;
            const column = { key: c.prop || `column-${index}`, title: c.label || '', width: dimension(c.width), minWidth: dimension(get(c, 'minWidth')), align: c.align, fixed: c.fixed === '' || c.fixed === true ? 'left' : c.fixed };
            if (c.type === 'expand') return { ...column, type: 'expand', width: dimension(c.width) || 48, renderExpand: (row, rowIndex) => render?.({ row, $index: rowIndex }) };
            if (c.type === 'selection') return { ...column, type: 'selection' };
            if (node.children?.header) column.title = () => node.children.header({ column: c, $index: index });
            if (get(c, 'showOverflowTooltip') !== undefined && get(c, 'showOverflowTooltip') !== false) column.ellipsis = { tooltip: true };
            column.render = (row, rowIndex) => render ? render({ row, $index: rowIndex, column: c }) : c.prop ? c.prop.split('.').reduce((value, field) => value?.[field], row) : '';
            return column;
          });
          const controlled = p.expandRowKeys !== undefined;
          const fullHeight = p.height === '100%';
          return h(N.NDataTable, mergeProps(attrs, {
            class: ['noc-data-table', 'noc-table'], data: p.data, columns,
            striped: p.stripe, bordered: p.border, singleLine: !p.border, size: size(p.size) || 'medium',
            rowKey: keyFor, rowClassName: (row, rowIndex) => typeof p.rowClassName === 'function' ? p.rowClassName({ row, rowIndex }) : p.rowClassName,
            rowProps: row => ({ onClick: event => emit('row-click', row, null, event) }),
            expandedRowKeys: controlled ? p.expandRowKeys : expanded.value,
            'onUpdate:expandedRowKeys': keys => {
              const previous = controlled ? p.expandRowKeys : expanded.value;
              const changed = keys.find(key => !previous.includes(key)) ?? previous.find(key => !keys.includes(key));
              expanded.value = keys;
              const row = p.data.find(item => keyFor(item) === changed);
              if (row) emit('expand-change', row, p.data.filter(item => keys.includes(keyFor(item))));
            },
            scrollX: columns.reduce((total, col) => total + (Number(col.width || col.minWidth) || 100), 0),
            flexHeight: fullHeight, maxHeight: fullHeight ? undefined : dimension(p.maxHeight || p.height),
            style: fullHeight ? { height: '100%' } : undefined
          }), { empty: slots.empty || (() => p.emptyText ?? (typeof tt === 'function' ? tt('common.noData') : '')) });
        };
      }
    }));
    app.component('ui-pagination', defineComponent({
      inheritAttrs: false,
      props: { currentPage: { type: Number, default: 1 }, pageSize: { type: Number, default: 10 }, total: Number, pageSizes: Array, pagerCount: Number, layout: String, disabled: Boolean },
      emits: ['update:currentPage', 'update:pageSize', 'current-change', 'size-change'],
      setup: (p, { attrs, emit }) => () => h(N.NPagination, mergeProps(attrs, {
        class: 'noc-pagination', page: p.currentPage, pageSize: p.pageSize, itemCount: p.total || 0, pageSizes: p.pageSizes,
        pageSlot: p.pagerCount || 7, showSizePicker: p.layout?.includes('sizes'), disabled: p.disabled,
        prev: ({ page }) => h(N.NButton, {
          quaternary: true, size: 'small', disabled: p.disabled || page <= 1,
          'aria-label': typeof currentLang === 'function' && currentLang().startsWith('en') ? 'Previous page' : typeof currentLang === 'function' && ['zh-HK', 'zh-TW'].includes(currentLang()) ? '上一頁' : '上一页'
        }, { default: () => '‹' }),
        next: ({ page, pageCount }) => h(N.NButton, {
          quaternary: true, size: 'small', disabled: p.disabled || page >= pageCount,
          'aria-label': typeof currentLang === 'function' && currentLang().startsWith('en') ? 'Next page' : typeof currentLang === 'function' && ['zh-HK', 'zh-TW'].includes(currentLang()) ? '下一頁' : '下一页'
        }, { default: () => '›' }),
        'onUpdate:page': value => { emit('update:currentPage', value); emit('current-change', value); },
        'onUpdate:pageSize': value => { emit('update:pageSize', value); emit('size-change', value); }
      }), p.layout?.includes('total') ? { prefix: () => typeof tt === 'function' ? tt('common.totalItems', { total: p.total || 0 }) : String(p.total || 0) } : undefined)
    }));
    app.component('ui-collapse', defineComponent({
      inheritAttrs: false, props: { modelValue: [Array, String, Number], accordion: Boolean }, emits: ['update:modelValue', 'change'],
      setup(p, { attrs, slots, emit }) {
        const internal = ref([]);
        return () => h(N.NCollapse, mergeProps(attrs, { class: 'noc-collapse', accordion: p.accordion, expandedNames: p.modelValue ?? internal.value,
          'onUpdate:expandedNames': value => { internal.value = value; emit('update:modelValue', value); emit('change', value); }
        }), slots);
      }
    }));
    app.component('ui-collapse-item', defineComponent({
      inheritAttrs: false, props: { name: [String, Number], title: String, disabled: Boolean },
      setup: (p, { attrs, slots }) => () => h(N.NCollapseItem, mergeProps(attrs, { class: 'noc-collapse-item', name: p.name, title: p.title, disabled: p.disabled }), { default: slots.default, header: slots.title || (() => p.title) })
    }));
    app.component('ui-tab-pane', marker('NocTabPane'));
    app.component('ui-tabs', defineComponent({
      inheritAttrs: false, props: { modelValue: [String, Number] }, emits: ['update:modelValue', 'tab-change'],
      setup(p, { attrs, slots, emit }) {
        const select = value => { emit('update:modelValue', value); emit('tab-change', value); };
        return () => {
          const panes = flatten(slots.default?.()).filter(node => node.type?.name === 'NocTabPane');
          return h(N.NTabs, mergeProps(attrs, { class: 'noc-tabs', role: 'tablist', value: p.modelValue, 'onUpdate:value': select }), {
            default: () => panes.map(node => {
              const pane = node.props || {};
              return h(N.NTabPane, {
                name: pane.name, tab: pane.label, disabled: pane.disabled,
                tabProps: {
                  role: 'tab', 'aria-selected': p.modelValue === pane.name,
                  'aria-disabled': !!pane.disabled, tabindex: p.modelValue === pane.name ? 0 : -1,
                  onKeydown: event => {
                    if (pane.disabled) return;
                    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(pane.name); return; }
                    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                    event.preventDefault();
                    const enabled = panes.filter(item => !item.props?.disabled);
                    const index = enabled.indexOf(node);
                    const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + enabled.length) % enabled.length;
                    select(enabled[next].props.name);
                    event.currentTarget.closest('[role="tablist"]')?.querySelectorAll('[role="tab"][aria-disabled="false"]')[next]?.focus();
                  }
                }
              }, { default: node.children?.default, tab: node.children?.label || (() => pane.label) });
            })
          });
        };
      }
    }));
    app.component('ui-descriptions-item', marker('NocDescriptionsItem'));
    app.component('ui-descriptions', defineComponent({
      inheritAttrs: false, props: { column: Number, border: Boolean },
      setup: (p, { attrs, slots }) => () => h(N.NDescriptions, mergeProps(attrs, { column: p.column, bordered: p.border, labelPlacement: 'left' }), {
        default: () => flatten(slots.default?.()).map(node => h(N.NDescriptionsItem, { label: node.props?.label, span: node.props?.span }, node.children))
      })
    }));
    ['tooltip', 'popover'].forEach(kind => app.component('ui-' + kind, defineComponent({
      inheritAttrs: false,
      props: { content: String, placement: String, trigger: [String, Array], showAfter: Number, popperClass: String, disabled: Boolean, width: [Number, String], effect: String },
      setup(p, { attrs, slots }) {
        const focused = ref(false);
        const dismissed = ref(false);
        return () => h(kind === 'tooltip' ? N.NTooltip : N.NPopover, mergeProps(attrs, {
          placement: p.placement || 'top', trigger: Array.isArray(p.trigger) ? 'hover' : p.trigger || 'hover', delay: p.showAfter || 0,
          show: p.disabled || dismissed.value ? false : focused.value ? true : undefined,
          disabled: p.disabled, class: p.popperClass, style: p.width ? { width: typeof p.width === 'number' ? p.width + 'px' : p.width } : undefined
        }), {
          trigger: () => {
            const nodes = (kind === 'popover' ? slots.reference : slots.default)?.() || [];
            if (!Array.isArray(p.trigger) || !p.trigger.includes('focus')) return nodes;
            return nodes.map(node => cloneVNode(node, {
              onFocusin: () => { dismissed.value = false; focused.value = true; },
              onFocusout: () => { focused.value = false; dismissed.value = false; },
              onMouseenter: () => { dismissed.value = false; },
              onKeydown: event => { if (event.key === 'Escape') { dismissed.value = true; focused.value = false; } },
            }));
          },
          default: kind === 'popover' ? slots.default : slots.content || (() => p.content)
        });
      }
    })));
    app.component('ui-image', defineComponent({
      inheritAttrs: false, props: { src: String, fit: String, previewSrcList: Array, previewTeleported: Boolean },
      setup: (p, { attrs, slots }) => () => h(N.NImage, mergeProps(attrs, { class: 'noc-image', src: p.src, objectFit: p.fit, previewSrc: p.previewSrcList?.[0], showToolbar: true, showToolbarTooltip: true }), slots)
    }));
    app.component('ui-timeline', defineComponent({ setup: (_, { slots }) => () => h(N.NTimeline, null, slots) }));
    app.component('ui-timeline-item', defineComponent({
      props: { timestamp: String, type: String, placement: String },
      setup: (p, { slots }) => () => h(N.NTimelineItem, { time: p.timestamp, type: p.type === 'primary' ? 'info' : p.type }, slots)
    }));
    app.component('ui-dialog', defineComponent({
      inheritAttrs: false,
      props: { modelValue: Boolean, title: String, width: [String, Number], top: String, closeOnClickModal: { type: Boolean, default: true }, closable: { type: Boolean, default: true }, closeOnEsc: { type: Boolean, default: true }, destroyOnClose: Boolean, appendToBody: Boolean },
      emits: ['update:modelValue', 'close', 'closed', 'opened'],
      setup(p, { attrs, slots, emit }) {
        let closeNotified = false;
        const notifyClose = () => { if (!closeNotified) { closeNotified = true; emit('close'); } };
        watch(() => p.modelValue, (value, old) => { if (value) closeNotified = false; else if (old) notifyClose(); });
        return () => h(N.NModal, {
          show: p.modelValue, preset: 'card', title: p.title, role: 'dialog', 'aria-label': p.title, 'aria-modal': 'true', closable: p.closable, closeOnEsc: p.closeOnEsc, maskClosable: p.closeOnClickModal,
          displayDirective: p.destroyOnClose ? 'if' : 'show',
          class: ['noc-dialog', attrs.class], style: [{ width: typeof p.width === 'number' ? p.width + 'px' : p.width || '680px', maxWidth: 'calc(100vw - 80px)', marginTop: p.top || '40px', marginBottom: '40px' }, attrs.style],
          'onUpdate:show': value => { emit('update:modelValue', value); if (!value) notifyClose(); },
          onAfterEnter: () => emit('opened'), onAfterLeave: () => emit('closed')
        }, { default: slots.default, footer: slots.footer ? () => h('div', { class: 'dialog-actions' }, slots.footer()) : undefined });
      }
    }));
    app.component('ui-drawer', defineComponent({
      inheritAttrs: false,
      props: { modelValue: Boolean, title: String, size: [String, Number], direction: String, appendToBody: Boolean, modal: { type: Boolean, default: true }, modalPenetrable: Boolean, lockScroll: { type: Boolean, default: true } },
      emits: ['update:modelValue', 'close'],
      setup: (p, { attrs, slots, emit }) => () => h(N.NDrawer, {
        show: p.modelValue, 'aria-label': p.title, width: dimension(p.size) || 520, placement: ({ rtl: 'right', ltr: 'left', ttb: 'top', btt: 'bottom' })[p.direction] || 'right',
        showMask: p.modal, blockScroll: p.lockScroll, maskClosable: p.modal,
        'onUpdate:show': value => { emit('update:modelValue', value); if (!value) emit('close'); }
      }, { default: () => h(N.NDrawerContent, mergeProps(attrs, { class: 'noc-drawer', title: p.title, closable: true }), slots) })
    }));
  };
})();
