/* Application form controls: preserve API payloads while rendering Naive UI. */
(function () {
  window.registerNocControls = function (app) {
    const { h, defineComponent, ref, watch, Fragment, mergeProps } = Vue;
    const n = naive;
    const valueProps = { modelValue: null, size: String, disabled: { type: Boolean, default: undefined } };
    const valueEvents = ['update:modelValue', 'change', 'input'];
    const size = (value) => value === 'default' ? 'medium' : value;
    const update = (emit, value) => {
      emit('update:modelValue', value);
      emit('input', value);
      emit('change', value);
    };
    const register = (name, options) => app.component(`ui-${name}`, defineComponent({ inheritAttrs: false, ...options }));

    // Compact actions share hit area, icon sizing, tooltip and keyboard semantics.
    register('action', {
      props: { label: { type: String, required: true }, icon: { type: String, required: true },
        type: String, loading: Boolean, disabled: Boolean },
      emits: ['click'],
      setup(p, { attrs, emit }) {
        const focused = ref(false);
        const dismissed = ref(false);
        return () => h(n.NTooltip, { role: 'tooltip', delay: 250, show: dismissed.value ? false : focused.value ? true : undefined }, {
          default: () => p.label,
          trigger: () => h(n.NButton, mergeProps(attrs, {
            class: 'noc-action', quaternary: true, size: 'small', attrType: 'button',
            type: p.type === 'danger' ? 'error' : p.type || 'default',
            loading: p.loading, disabled: p.disabled, 'aria-label': p.label,
            onFocus: () => { dismissed.value = false; focused.value = true; },
            onMouseenter: () => { dismissed.value = false; },
            onKeydown: event => { if (event.key === 'Escape') { dismissed.value = true; focused.value = false; } },
            onBlur: () => { focused.value = false; },
            onClick: event => { dismissed.value = true; focused.value = false; event.stopPropagation(); emit('click', event); },
          }), { icon: () => h(n.NIcon, { size: 18, 'aria-hidden': true }, {
            default: () => h(ElementPlusIconsVue[p.icon]),
          }) }),
        });
      },
    });

    register('button', {
      props: { type: String, size: String, icon: [Object, Function, String], text: Boolean, link: Boolean,
        plain: Boolean, circle: Boolean, nativeType: String },
      setup(p, { attrs, slots }) {
        return () => h(n.NButton, { ...attrs, type: p.type === 'danger' ? 'error' : p.type,
          size: size(p.size), text: p.text || p.link, secondary: p.plain, circle: p.circle,
          attrType: p.nativeType || 'button' }, {
          ...slots, ...(p.icon ? { icon: () => h(p.icon) } : {}),
        });
      },
    });
    register('input', {
      props: { ...valueProps, type: String, rows: [Number, String], showPassword: Boolean,
        resize: String, id: String, autocomplete: String, spellcheck: [Boolean, String] },
      emits: valueEvents,
      setup(p, { attrs, slots, emit, expose }) {
        const control = ref(null);
        expose({ focus: () => control.value?.focus(), blur: () => control.value?.blur() });
        return () => h(n.NInput, { ...attrs, ref: control, value: p.modelValue == null ? '' : String(p.modelValue),
          size: size(p.size), disabled: p.disabled, type: ['password', 'textarea'].includes(p.type) ? p.type : 'text',
          rows: p.rows == null ? undefined : Number(p.rows), showPasswordOn: p.showPassword ? 'click' : undefined,
          inputProps: { id: p.id, autocomplete: p.autocomplete, spellcheck: p.spellcheck,
            // Omit type for passwords: Naive UI owns it while toggling visibility.
            ...(p.type === 'email' ? { type: 'email' } : {}),
            'aria-label': attrs['aria-label'], 'aria-invalid': attrs['aria-invalid'],
            'aria-describedby': attrs['aria-describedby'] },
          'onUpdate:value': (value) => update(emit, value),
        }, slots);
      },
    });
    // Options are declarative metadata, never mounted as DOM inside NSelect.
    register('option', { props: { value: null, label: null, disabled: Boolean }, setup: () => () => null });
    function optionsFrom(nodes, result = []) {
      for (const node of nodes || []) {
        if (node.type === Fragment || Array.isArray(node.children)) optionsFrom(node.children, result);
        else if (node.props && Object.prototype.hasOwnProperty.call(node.props, 'value')) {
          result.push({ label: node.props.label ?? String(node.props.value), value: node.props.value,
            disabled: node.props.disabled === '' || node.props.disabled === true });
        }
      }
      return result;
    }
    register('select', {
      props: { ...valueProps, multiple: Boolean, filterable: Boolean, allowCreate: Boolean, defaultFirstOption: Boolean },
      emits: valueEvents,
      setup(p, { attrs, slots, emit }) {
        // NSelect accepts strings/numbers. Boolean options retain their API type.
        const encode = (value) => typeof value === 'boolean' ? `__noc_bool_${value}` : value;
        const decode = (value) => value === '__noc_bool_true' ? true : value === '__noc_bool_false' ? false : value;
        const map = (value, fn) => Array.isArray(value) ? value.map(fn) : fn(value);
        return () => {
          const options = optionsFrom(slots.default?.());
          // Filters use '' for no selection; Naive needs null to display a placeholder.
          // A deliberately declared empty-string option still remains selectable.
          const empty = !p.multiple && p.modelValue === '' && !options.some((option) => option.value === '');
          return h(n.NSelect, { ...attrs, size: size(p.size), disabled: p.disabled,
            multiple: p.multiple, filterable: p.filterable || p.allowCreate, tag: p.allowCreate,
            value: empty ? null : map(p.modelValue ?? (p.multiple ? [] : null), encode),
            options: options.map((option) => ({ ...option, value: encode(option.value) })),
            'onUpdate:value': (value) => update(emit, value == null && !p.multiple ? '' : map(value, decode)),
          }, { action: slots.action });
        };
      },
    });
    register('form', {
      props: { model: Object, rules: Object, labelPosition: String, labelWidth: [String, Number], disabled: Boolean },
      setup(p, { attrs, slots, expose }) {
        const control = ref(null);
        expose({ validate: (...args) => control.value.validate(...args), clearValidate: () => control.value?.restoreValidation() });
        return () => h(n.NForm, { ...attrs, ref: control, model: p.model, rules: p.rules, disabled: p.disabled,
          labelPlacement: p.labelPosition === 'top' ? 'top' : 'left',
          labelWidth: p.labelWidth ? parseInt(p.labelWidth, 10) : undefined,
        }, slots);
      },
    });
    register('form-item', {
      props: { prop: String, label: String },
      setup: (p, { attrs, slots }) => () => h(n.NFormItem, { ...attrs, path: p.prop, label: p.label }, slots),
    });
    register('checkbox', {
      props: { ...valueProps, trueLabel: { default: true }, falseLabel: { default: false } },
      emits: valueEvents,
      setup: (p, { attrs, slots, emit }) => () => h(n.NCheckbox, {
        ...attrs, checked: p.modelValue, checkedValue: p.trueLabel, uncheckedValue: p.falseLabel,
        size: size(p.size), disabled: p.disabled,
        'onUpdate:checked': value => update(emit, value),
      }, slots),
    });
    for (const [name, component, field] of [ ['switch', n.NSwitch, 'value'],
      ['radio-group', n.NRadioGroup, 'value'], ['input-number', n.NInputNumber, 'value'] ]) {
      register(name, {
        props: { ...valueProps, activeText: String, inactiveText: String, inlinePrompt: Boolean }, emits: valueEvents,
        setup(p, { attrs, slots, emit }) {
          return () => h(component, { ...attrs, [field]: p.modelValue, size: size(p.size), disabled: p.disabled,
            [`onUpdate:${field}`]: (value) => update(emit, value) }, {
            ...slots, ...(name === 'switch' && p.inlinePrompt ? {
              checked: () => p.activeText, unchecked: () => p.inactiveText,
            } : {}),
          });
        },
      });
    }
    register('radio-button', {
      props: { value: null }, setup: (p, { attrs, slots }) => () => h(n.NRadioButton, { ...attrs, value: p.value }, slots),
    });
    register('date-picker', {
      props: { ...valueProps, type: String, format: String, valueFormat: String }, emits: valueEvents,
      setup(p, { attrs, emit }) {
        // Naive UI uses date-fns tokens; keep backend-facing local datetime strings unchanged.
        const format = (value) => value?.replace(/YYYY/g, 'yyyy').replace(/DD/g, 'dd');
        return () => h(n.NDatePicker, { ...attrs, type: p.type || 'date', size: size(p.size), disabled: p.disabled,
          formattedValue: p.modelValue || null, valueFormat: format(p.valueFormat || 'YYYY-MM-DD'),
          format: format(p.format || p.valueFormat || 'YYYY-MM-DD'),
          'onUpdate:formattedValue': (value) => update(emit, value || ''),
        });
      },
    });
    register('autocomplete', {
      props: { ...valueProps, fetchSuggestions: Function }, emits: valueEvents,
      setup(p, { attrs, emit }) {
        const options = ref([]);
        const interacting = ref(false);
        let revision = 0;
        function suggest(value) {
          const current = ++revision;
          p.fetchSuggestions?.(value || '', (items) => {
            if (current === revision) options.value = items.map((item) => ({ label: item.value, value: item.value }));
          });
        }
        watch(() => p.modelValue, suggest, { immediate: true });
        return () => h(n.NAutoComplete, { ...attrs, value: p.modelValue || '', options: options.value,
          size: size(p.size), disabled: p.disabled, onFocus: () => suggest(p.modelValue),
          // Modal autofocus should not open a menu during the entrance transform.
          getShow: () => interacting.value,
          onPointerdown: () => { interacting.value = true; },
          onKeydown: event => { if (event.key !== 'Tab' && event.key !== 'Escape') interacting.value = true; },
          onBlur: () => { interacting.value = false; },
          'onUpdate:value': (value) => update(emit, value),
        });
      },
    });
    register('upload', {
      props: { fileList: Array, autoUpload: { type: Boolean, default: true }, multiple: Boolean,
        drag: Boolean, limit: Number, onChange: Function, onRemove: Function, onExceed: Function },
      emits: ['update:fileList'],
      setup(p, { attrs, slots, emit }) {
        const local = ref([]);
        const toNative = (file) => ({ ...file, id: String(file.id ?? file.uid),
          status: file.status === 'ready' ? 'pending' : (file.status || 'pending'), file: file.file || file.raw || null });
        const toApplication = (file) => ({ ...file, uid: file.id, raw: file.file });
        // Import uses a one-way list plus callbacks; extraction uses v-model:file-list.
        watch(() => p.fileList, (files) => { local.value = (files || []).map(toNative); }, { immediate: true });
        return () => h(n.NUpload, { ...attrs, fileList: local.value, defaultUpload: p.autoUpload,
          multiple: p.multiple, directoryDnd: false,
          onBeforeUpload: ({ file }) => {
            if (p.limit && local.value.length >= p.limit) {
              p.onExceed?.([file.file], local.value.map(toApplication));
              return false;
            }
            return true;
          },
          onChange: ({ file, fileList }) => {
            local.value = fileList;
            const files = fileList.map(toApplication);
            emit('update:fileList', files);
            if (file.status !== 'removed') p.onChange?.(toApplication(file), files);
          },
          onRemove: ({ file, fileList }) => p.onRemove?.(toApplication(file), fileList.map(toApplication)),
        }, { default: () => p.drag ? h(n.NUploadDragger, null, slots) : slots.default?.() });
      },
    });
  };
})();
