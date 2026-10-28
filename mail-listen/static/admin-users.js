/* Administrator account and mailbox permissions. */
const ViewUsers = defineComponent({
  name: 'ViewUsers',
  setup() {
    const users = ref([]);
    const mailboxes = ref([]);
    const selected = ref(null);
    const grants = reactive({});
    const busy = ref(false);
    const loading = ref(false);
    const form = reactive({username: '', display_name: '', password: ''});
    const resetPassword = ref('');
    async function load() {
      loading.value = true;
      try {
        [users.value, mailboxes.value] = await Promise.all([
          requestJson('/api/users'), requestJson('/api/system/mail-accounts')]);
      } catch (error) { NocMessage.error(error.message); }
      finally { loading.value = false; }
    }
    async function selectUser(user) {
      selected.value = null;
      resetPassword.value = '';
      try {
        const assigned = await requestJson(`/api/users/${user.id}/mailboxes`);
        for (const key of Object.keys(grants)) delete grants[key];
        for (const box of mailboxes.value) grants[box.id] = 'none';
        for (const grant of assigned) grants[grant.account_id] = grant.can_operate ? 'operate' : 'view';
        selected.value = user;
      } catch (error) { NocMessage.error(error.message); }
    }
    async function perform(action) {
      busy.value = true;
      try { await action(); NocMessage.success('已保存'); }
      catch (error) { NocMessage.error(error.message); }
      finally { busy.value = false; }
    }
    async function create() {
      await perform(async () => {
        const user = await requestJson('/api/users', {method: 'POST', body: JSON.stringify(form)});
        Object.assign(form, {username: '', display_name: '', password: ''});
        await load();
        await selectUser(user);
      });
    }
    async function saveGrants() {
      await perform(async () => {
        await requestFull(`/api/users/${selected.value.id}/mailboxes`, {method: 'PUT', body: JSON.stringify({
          grants: mailboxes.value.filter(box => grants[box.id] !== 'none').map(box => ({
            account_id: box.id, can_operate: grants[box.id] === 'operate'}))})});
      });
    }
    async function updateUser(body) {
      await perform(async () => {
        const id = selected.value.id;
        await requestFull(`/api/users/${id}`, {method: 'PATCH', body: JSON.stringify(body)});
        await load();
        await selectUser(users.value.find(user => user.id === id));
      });
    }
    async function releasePortal() {
      await perform(async () => {
        await requestFull(`/api/users/${selected.value.id}/portal-session`, {method: 'DELETE'});
      });
    }
    onMounted(load);
    return {users, mailboxes, selected, grants, busy, loading, form, resetPassword,
      selectUser, create, saveGrants, updateUser, releasePortal};
  },
  template: `
    <div class="users-page" v-loading="loading">
      <div class="page-head"><div><h2>用户与邮箱授权</h2><p class="muted">管理员管理用户、邮箱与业务配置；综调登录与上报由普通用户操作。邮箱授权同时适用于历史邮件和相关任务。</p></div></div>
      <section class="block-section"><h3>创建普通用户</h3>
        <form class="user-create-form" @submit.prevent="create">
          <label>用户名<ui-input v-model="form.username" aria-label="新用户用户名" placeholder="字母、数字或下划线"></ui-input></label>
          <label>显示名称<ui-input v-model="form.display_name" aria-label="新用户显示名称" placeholder="例如：张三"></ui-input></label>
          <label>初始密码<ui-input v-model="form.password" aria-label="新用户初始密码" type="password" show-password placeholder="10–128 位"></ui-input></label>
          <ui-button type="primary" :loading="busy" @click="create">创建账号</ui-button>
        </form>
      </section>
      <div class="users-grid">
        <section class="block-section"><h3>普通用户</h3>
          <p v-if="!users.length" class="muted">还没有普通用户，请先创建账号。</p>
          <button v-for="user in users" :key="user.id" class="user-choice" :class="{'is-selected': selected?.id === user.id}" @click="selectUser(user)">
            <strong>{{ user.display_name }}</strong><span>{{ user.username }} · {{ user.enabled ? '已启用' : '已停用' }}</span>
          </button>
        </section>
        <section class="block-section" v-if="selected">
          <h3>{{ selected.display_name }} · 邮箱授权</h3>
          <p class="muted">查看并操作：允许确认、修改、回复和上报。未授权邮箱的邮件、任务及文件均不可访问。</p>
          <p v-if="!mailboxes.length">请先在“邮箱账号”中配置监听邮箱。</p>
          <div class="mailbox-grant" v-for="box in mailboxes" :key="box.id">
            <div><strong>{{ box.name || box.email_address }}</strong><p class="muted">{{ box.email_address }}</p></div>
            <ui-select v-model="grants[box.id]" :aria-label="box.email_address + ' 权限'">
              <ui-option value="none" label="未授权"></ui-option><ui-option value="view" label="仅查看"></ui-option><ui-option value="operate" label="查看并操作"></ui-option>
            </ui-select>
          </div>
          <ui-button type="primary" :loading="busy" @click="saveGrants">保存邮箱授权</ui-button>
          <hr class="user-divider">
          <h3>账号管理</h3><p class="muted">停用账号或重置密码后，该用户的工作台登录立即失效。</p>
          <div class="user-account-actions">
            <ui-button :loading="busy" @click="updateUser({enabled: !selected.enabled})">{{ selected.enabled ? '停用账号' : '启用账号' }}</ui-button>
            <ui-button :loading="busy" @click="releasePortal">解除综调绑定</ui-button>
            <ui-input v-model="resetPassword" type="password" show-password aria-label="重置密码" placeholder="新密码（10–128 位）"></ui-input>
            <ui-button :disabled="resetPassword.length < 10" :loading="busy" @click="updateUser({password: resetPassword})">重置密码</ui-button>
          </div>
        </section>
        <section v-else class="block-section muted">选择用户，设置邮箱访问权限。</section>
      </div>
    </div>`,
});
