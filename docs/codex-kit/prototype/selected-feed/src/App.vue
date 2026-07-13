<script setup>
import { computed, ref } from "vue";
import {
  Bookmark,
  Book,
  CheckCircle,
  EmptyPage,
  FilterList,
  GraphUp,
  List,
  NavArrowRight,
  Page,
  Reports,
  Search,
  Settings,
  ShieldCheck,
  Sparks,
  Star,
  UserCircle,
  WarningCircle,
  Xmark,
} from "iconoir-vue/regular";
import { feedItems, tabs } from "./data.js";

const navItems = [
  { label: "今日精选", icon: Star },
  { label: "全部动态", icon: List },
  { label: "数字化", icon: GraphUp },
  { label: "安全情报", icon: ShieldCheck },
  { label: "行业日报", icon: Reports },
  { label: "收藏", icon: Bookmark },
];

const activeTab = ref("全部");
const selectedNav = ref("今日精选");
const query = ref("");
const filterOpen = ref(false);
const onlyVerified = ref(false);
const savedIds = ref(new Set());
const evidenceItem = ref(null);
const digitalCategories = new Set(["数字化案例", "期刊论文", "软件设备"]);
const safetyCategories = new Set(["安全规定", "安全案例"]);

const visibleItems = computed(() => {
  const normalizedQuery = query.value.trim().toLowerCase();
  return feedItems.filter((item) => {
    const matchesTab = activeTab.value === "全部" || item.category === activeTab.value;
    const matchesNav =
      (selectedNav.value !== "数字化" || digitalCategories.has(item.category)) &&
      (selectedNav.value !== "安全情报" || safetyCategories.has(item.category)) &&
      (selectedNav.value !== "收藏" || savedIds.value.has(item.id));
    const matchesQuery = !normalizedQuery || [item.title, item.summary, item.source, ...item.tags].join(" ").toLowerCase().includes(normalizedQuery);
    const matchesVerified = !onlyVerified.value || item.status === "verified";
    return matchesNav && matchesTab && matchesQuery && matchesVerified;
  });
});

const emptyTitle = computed(() => selectedNav.value === "收藏" ? "暂时没有收藏" : "当前筛选下没有结果");
const emptyDescription = computed(() => selectedNav.value === "收藏" ? "在信息卡右侧点击收藏后，可在这里集中查看。" : "可清除搜索词或关闭“仅显示已复核”。");

function selectNav(label) {
  selectedNav.value = label;
  activeTab.value = "全部";
}

function toggleSaved(id) {
  const next = new Set(savedIds.value);
  next.has(id) ? next.delete(id) : next.add(id);
  savedIds.value = next;
}

function clearFilters() {
  query.value = "";
  onlyVerified.value = false;
  activeTab.value = "全部";
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-lockup" aria-label="四川路桥智安情报">
        <span>四川路桥</span><strong>智安情报</strong>
      </div>
      <nav aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          :class="{ 'is-active': selectedNav === item.label }"
          type="button"
          @click="selectNav(item.label)"
        >
          <component :is="item.icon" :width="22" :height="22" :stroke-width="selectedNav === item.label ? 2 : 1.5" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-footer">
        <button class="admin-link" type="button">
          <Settings :width="21" :height="21" />
          <span>管理入口</span>
          <NavArrowRight :width="18" :height="18" />
        </button>
        <div class="user-card">
          <UserCircle :width="38" :height="38" />
          <div><strong>张经理</strong><span>项目管理部</span></div>
        </div>
      </div>
    </aside>

    <header class="mobile-header">
      <div class="brand-lockup" aria-label="四川路桥智安情报">
        <span>四川路桥</span><strong>智安情报</strong>
      </div>
      <button class="icon-button" type="button" aria-label="打开筛选" @click="filterOpen = true">
        <FilterList :width="22" :height="22" />
      </button>
    </header>

    <main class="content-shell">
      <header class="page-header">
        <div>
          <span class="mobile-section-label">{{ selectedNav }}</span>
          <h1>{{ selectedNav }}</h1>
          <p>2026年7月13日 星期一 <span>·</span> 数据每10分钟更新</p>
        </div>
        <div class="header-actions">
          <label class="search-box">
            <span class="sr-only">搜索</span>
            <input v-model="query" placeholder="搜索关键词/来源/正文…" />
            <Search :width="22" :height="22" />
          </label>
          <button class="filter-button" type="button" @click="filterOpen = !filterOpen">
            <FilterList :width="20" :height="20" />筛选
          </button>
          <div class="filter-popover" :class="{ 'is-open': filterOpen }" :aria-hidden="!filterOpen">
            <div class="filter-heading">
              <div><strong>筛选条件</strong><span>筛选只影响当前信息流</span></div>
              <button class="icon-button" type="button" aria-label="关闭筛选" @click="filterOpen = false">
                <Xmark :width="20" :height="20" />
              </button>
            </div>
            <label class="check-row">
              <input v-model="onlyVerified" type="checkbox" />
              <span>仅显示已人工复核</span>
            </label>
            <p>安全规定与安全案例仍受服务端发布投影和权限门禁约束。</p>
          </div>
        </div>
      </header>

      <div class="tabs-row" role="tablist" aria-label="内容类型">
        <button
          v-for="tab in tabs"
          :key="tab"
          role="tab"
          :aria-selected="activeTab === tab"
          :class="{ 'is-active': activeTab === tab }"
          type="button"
          @click="activeTab = tab"
        >{{ tab }}</button>
      </div>

      <section class="feed" aria-live="polite">
        <article v-for="item in visibleItems" :key="item.id" class="feed-row">
          <time :datetime="`2026-07-13T${item.time}:00+08:00`">{{ item.time }}</time>
          <span class="timeline-dot" aria-hidden="true" />
          <div class="feed-card">
            <div class="feed-card-main">
              <div class="meta-line">
                <span>来源：{{ item.source }}</span><span aria-hidden="true">·</span><span>{{ item.time }}</span>
                <span aria-hidden="true">·</span><b>【{{ item.category }}】</b>
                <span v-if="item.status === 'review'" class="status-badge status-review">
                  <WarningCircle :width="14" :height="14" />待人工复核
                </span>
                <span v-else-if="item.status === 'vendor'" class="status-badge status-vendor">厂商声明</span>
                <span v-else class="status-badge status-verified">
                  <CheckCircle :width="14" :height="14" />{{ item.evidenceStatus }}
                </span>
              </div>
              <h2>{{ item.title }}</h2>
              <p class="summary">{{ item.summary }}</p>
              <p class="relevance"><strong>与四川路桥的关系：</strong>{{ item.relevance }}</p>
              <div class="tag-list" aria-label="内容标签"><span v-for="tag in item.tags" :key="tag">{{ tag }}</span></div>
            </div>
            <aside class="card-evidence" aria-label="相关度与证据">
              <div class="score-block"><strong>{{ item.score }}</strong><span>相关度</span></div>
              <button
                class="bookmark-button"
                :class="{ 'is-saved': savedIds.has(item.id) }"
                type="button"
                :aria-label="savedIds.has(item.id) ? '取消收藏' : '收藏'"
                :aria-pressed="savedIds.has(item.id)"
                @click="toggleSaved(item.id)"
              ><Bookmark :width="24" :height="24" /></button>
              <button class="evidence-button" type="button" @click="evidenceItem = item">查看证据</button>
              <dl>
                <div><dt><Page :width="17" :height="17" />证据</dt><dd>{{ item.evidence }}</dd></div>
                <div><dt><ShieldCheck :width="17" :height="17" />状态</dt><dd :class="`evidence-${item.status}`">{{ item.evidenceStatus }}</dd></div>
              </dl>
            </aside>
          </div>
        </article>

        <div v-if="visibleItems.length === 0" class="empty-state">
          <EmptyPage :width="34" :height="34" />
          <h2>{{ emptyTitle }}</h2><p>{{ emptyDescription }}</p>
          <button class="secondary-button" type="button" @click="clearFilters">清除筛选</button>
        </div>
      </section>

      <footer class="page-footer">
        <Book :width="18" :height="18" /><span>摘要由 AI 辅助整理，重要信息请以原文和人工审核结果为准。</span><Sparks :width="18" :height="18" />
      </footer>
    </main>

    <button
      class="drawer-backdrop"
      :class="{ 'is-open': evidenceItem }"
      :tabindex="evidenceItem ? 0 : -1"
      type="button"
      aria-label="关闭证据面板"
      @click="evidenceItem = null"
    />
    <aside class="evidence-drawer" :class="{ 'is-open': evidenceItem }" :aria-hidden="!evidenceItem">
      <template v-if="evidenceItem">
        <header>
          <div><span class="eyebrow">证据核验</span><h2>{{ evidenceItem.category }}</h2></div>
          <button class="icon-button" type="button" aria-label="关闭证据面板" @click="evidenceItem = null">
            <Xmark :width="22" :height="22" />
          </button>
        </header>
        <section>
          <h3>{{ evidenceItem.title }}</h3>
          <div class="evidence-summary">
            <CheckCircle :width="22" :height="22" />
            <div><strong>{{ evidenceItem.evidenceStatus }}</strong><span>来源权威等级 {{ evidenceItem.authority }} · 证据覆盖 1/1</span></div>
          </div>
        </section>
        <section><h4>证据定位</h4><p>{{ evidenceItem.locator }}</p><blockquote>{{ evidenceItem.excerpt }}</blockquote></section>
        <section><h4>平台边界</h4><p>本页展示证据与平台整理结果，不替代正式制度、专业审查和现场安全决策。</p></section>
        <footer><button class="secondary-button" type="button">复制内部引用</button><button class="primary-button" type="button">查看原文</button></footer>
      </template>
    </aside>
  </div>
</template>
