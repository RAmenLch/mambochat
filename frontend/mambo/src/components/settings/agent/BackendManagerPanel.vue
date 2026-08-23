<!-- frontend/mambo/src/components/settings/agent/BackendManagerPanel.vue -->
<template>
  <div class="backend-manager-panel">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon> {{ $t('backend.new') }}
      </el-button>
      <el-button @click="handleShowPublicKey">
        <el-icon><Key /></el-icon> {{ $t('backend.showPublicKey') }}
      </el-button>
    </div>

    <!-- Backend 列表 -->
    <el-table :data="backendList" v-loading="isLoading" border stripe class="backend-table">
      <el-table-column prop="name" :label="$t('backend.name')" width="150" />
      <el-table-column prop="backendType" :label="$t('backend.type')" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.backendType === 'ssh'" size="small" type="info">SSH</el-tag>
          <el-tag v-else-if="row.backendType === 'api'" size="small" type="success">API</el-tag>
          <el-tag v-else-if="row.backendType === 'resource'" size="small" type="warning">Resource</el-tag>
          <el-tag v-else-if="row.backendType === 'local'" size="small" type="danger">Local</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('backend.host')" min-width="220">
        <template #default="{ row }">
          <template v-if="row.backendType === 'ssh'">
            {{ row.configData.username }}@{{ row.configData.hostname }}:{{ row.configData.port || 22 }}
          </template>
          <template v-else-if="row.backendType === 'api'">
            <div class="api-info">
              <span class="api-label">{{ $t('backend.id') }}:</span>
              <span class="api-id">{{ row.id }}</span>
              <el-tag
                v-if="clientStatusMap[row.id]"
                :type="clientStatusMap[row.id]?.connected ? 'success' : 'danger'"
                size="small"
                class="status-tag"
              >
                {{ clientStatusMap[row.id]?.connected ? $t('backend.connected') : $t('backend.offline') }}
              </el-tag>
            </div>
          </template>
          <template v-else-if="row.backendType === 'resource'">
            <div class="api-info">
              <span class="api-label">{{ $t('backend.resource') }}</span>
              <el-tooltip :content="$t('backend.resourceIdTooltip', { id: row.configData.resource_id })" placement="top">
                <span class="api-id resource-path">{{ resolvedResourcePaths.get(row.configData.resource_id) || row.configData.resource_id }}</span>
              </el-tooltip>
            </div>
          </template>
          <template v-else-if="row.backendType === 'local'">
            <div class="api-info">
              <span class="api-label">{{ row.configData.root_dir || '~' }}</span>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="description" :label="$t('backend.description')" show-overflow-tooltip />
      <el-table-column :label="$t('common.action.operate')" width="250" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleEdit(row)">{{ $t('common.action.edit') }}</el-button>
          <el-button link type="success" @click="handleDuplicate(row.id)">{{ $t('backend.duplicate') }}</el-button>
          <el-popconfirm :title="$t('common.msg.confirmDelete')" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger">{{ $t('common.action.delete') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Backend 表单弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('backend.edit') : $t('backend.new')"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="currentRules" label-width="120px" v-loading="isSaving">
        <el-form-item :label="$t('backend.name')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('backend.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('backend.description')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('backend.type')" prop="backendType">
          <el-select v-model="form.backendType" :disabled="isEdit" style="width: 100%" @change="handleTypeChange">
            <el-option :label="$t('backend.typeSsh')" value="ssh" />
            <el-option :label="$t('backend.typeApi')" value="api" />
            <el-option :label="$t('backend.typeResource')" value="resource" />
            <el-option :label="$t('backend.typeLocal')" value="local" />
          </el-select>
        </el-form-item>

        <!-- SSH 配置 -->
        <template v-if="form.backendType === 'ssh'">
          <el-divider content-position="left">{{ $t('backend.sshConfig') }}</el-divider>
          <el-form-item label="Hostname" prop="configData.hostname">
            <el-input v-model="form.configData.hostname" :placeholder="$t('backend.hostPlaceholder')" />
          </el-form-item>
          <el-form-item label="Username" prop="configData.username">
            <el-input v-model="form.configData.username" placeholder="root" />
          </el-form-item>
          <el-form-item label="Port" prop="configData.port">
            <el-input-number v-model="form.configData.port" :min="1" :max="65535" controls-position="right" />
          </el-form-item>
          <el-form-item label="Password" prop="configData.password">
            <el-input v-model="form.configData.password" type="password" show-password :placeholder="$t('backend.passwordPlaceholder')" />
          </el-form-item>
        </template>

        <!-- API 配置 -->
        <template v-if="form.backendType === 'api'">
          <el-divider content-position="left">{{ $t('backend.apiConfig') }}</el-divider>
          <el-form-item label="API Key" prop="configData.api_key">
            <el-input v-model="form.configData.api_key" :type="showApiKey ? 'text' : 'password'" show-password :placeholder="$t('backend.apiKeyPlaceholder')">
              <template #append>
                <el-button @click="showApiKey = !showApiKey">
                  <el-icon><View v-if="!showApiKey" /><Hide v-else /></el-icon>
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-divider content-position="left">{{ $t('backend.editPermission') }}</el-divider>

          <el-form-item :label="$t('backend.editMode')">
            <el-radio-group v-model="editMode" @change="onEditModeChange">
              <el-radio value="whitelist">{{ $t('backend.whitelistModePath') }}</el-radio>
              <el-radio value="blacklist">{{ $t('backend.blacklistModePath') }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="editMode === 'whitelist'" :label="$t('backend.whitelistLabel')" prop="configData.edit_whitelist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_whitelist"
                :key="'wl-api-' + idx"
                closable
                size="small"
                @close="removeFromWhitelist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isWlInputVisible"
                ref="wlInputRef"
                v-model="newWlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.wlInputPlaceholder')"
                @keyup.enter="addWhitelistItem"
                @blur="addWhitelistItem"
              />
              <el-button v-else size="small" @click="openWlInput">{{ $t('backend.addPath') }}</el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.wlPathTip') }}</div>
          </el-form-item>
          <el-form-item v-if="editMode === 'blacklist'" :label="$t('backend.blacklistLabel')" prop="configData.edit_blacklist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_blacklist"
                :key="'bl-api-' + idx"
                closable
                size="small"
                type="danger"
                @close="removeFromBlacklist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isBlInputVisible"
                ref="blInputRef"
                v-model="newBlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.blInputPlaceholder')"
                @keyup.enter="addBlacklistItem"
                @blur="addBlacklistItem"
              />
              <el-button v-else size="small" type="danger" plain @click="openBlInput">{{ $t('backend.addPath') }}</el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.blPathTip') }}</div>
          </el-form-item>
          <div class="api-tip">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                <span v-html="$t('backend.apiTipTitle')"></span><br/>
                <code>{{ $t('backend.apiTipCommand', { id: '<ID>', key: '<KEY>' }) }}</code>
              </template>
            </el-alert>
          </div>
        </template>

        <!-- Resource 配置 -->
        <template v-if="form.backendType === 'resource'">
          <el-divider content-position="left">{{ $t('backend.resourceConfig') }}</el-divider>
          <el-form-item label="Resource ID" prop="configData.resource_id">
            <el-select
              v-model="form.configData.resource_id"
              :placeholder="$t('backend.resourceIdPlaceholder')"
              filterable
              clearable
              style="width: 100%"
              :loading="isResourceFoldersLoading"
              @visible-change="onResourceFolderDropdownVisible"
            >
              <el-option
                v-for="folder in resourceFolderOptions"
                :key="folder.id"
                :label="folder.name"
                :value="folder.id"
              >
                <span>{{ folder.name }}</span>
                <span class="resource-mount-path" style="float: right; color: var(--el-text-color-secondary); font-size: 12px;" v-if="folder.path">{{ folder.path }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('backend.enableVersionEditing')">
            <div class="tools-config-row">
              <el-switch v-model="form.configData.enable_version_editing" />
              <span class="tools-config-label" style="margin-left: 12px;">{{ form.configData.enable_version_editing ? $t('backend.versionEditingEnabled') : $t('backend.versionEditingDisabled') }}</span>
            </div>
            <div class="tools-config-tip">{{ $t('backend.versionEditingTip') }}</div>
          </el-form-item>
          <el-divider content-position="left">{{ $t('backend.editPermission') }}</el-divider>

          <el-form-item :label="$t('backend.editMode')">
            <el-radio-group v-model="editMode" @change="onEditModeChange">
              <el-radio value="whitelist">{{ $t('backend.whitelistModePath') }}</el-radio>
              <el-radio value="blacklist">{{ $t('backend.blacklistModePath') }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="editMode === 'whitelist'" :label="$t('backend.whitelistLabel')" prop="configData.edit_whitelist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_whitelist"
                :key="'wl-res-' + idx"
                closable
                size="small"
                @close="removeFromWhitelist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isWlInputVisible"
                ref="wlInputRef"
                v-model="newWlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.wlInputPlaceholder')"
                @keyup.enter="addWhitelistItem"
                @blur="addWhitelistItem"
              />
              <el-button v-else size="small" @click="openWlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" @click="openResPicker('whitelist')">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseResourceTree') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.resourcePickerTip') }}</div>
          </el-form-item>
          <el-form-item v-if="editMode === 'blacklist'" :label="$t('backend.blacklistLabel')" prop="configData.edit_blacklist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_blacklist"
                :key="'bl-res-' + idx"
                closable
                size="small"
                type="danger"
                @close="removeFromBlacklist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isBlInputVisible"
                ref="blInputRef"
                v-model="newBlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.blInputPlaceholder')"
                @keyup.enter="addBlacklistItem"
                @blur="addBlacklistItem"
              />
              <el-button v-else size="small" type="danger" plain @click="openBlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" type="danger" plain @click="openResPicker('blacklist')">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseResourceTree') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.resourcePickerTip') }}</div>
          </el-form-item>
          <div class="api-tip">
            <el-alert type="success" :closable="false" show-icon>
              <template #title>
                {{ $t('backend.resourceTipTitle') }}<br/>
                <span v-html="$t('backend.resourceTipNote')"></span>
              </template>
            </el-alert>
          </div>
        </template>

        <!-- Local 配置 -->
        <template v-if="form.backendType === 'local'">
          <el-alert type="warning" :closable="false" show-icon class="local-warning">
            <template #title>
              {{ $t('backend.localWarning') }}
            </template>
          </el-alert>

          <el-divider content-position="left">{{ $t('backend.localConfig') }}</el-divider>

          <el-form-item label="Root Dir" prop="configData.root_dir">
            <el-input v-model="form.configData.root_dir" :placeholder="$t('backend.rootDirPlaceholder')" />
          </el-form-item>

          <el-divider content-position="left">{{ $t('backend.editPermission') }}</el-divider>

          <el-form-item :label="$t('backend.editMode')">
            <el-radio-group v-model="editMode" @change="onEditModeChange">
              <el-radio value="whitelist">{{ $t('backend.whitelistModeDir') }}</el-radio>
              <el-radio value="blacklist">{{ $t('backend.blacklistModeDir') }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="editMode === 'whitelist'" :label="$t('backend.whitelistLabel')" prop="configData.edit_whitelist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_whitelist"
                :key="'wl-local-' + idx"
                closable
                size="small"
                @close="removeFromWhitelist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isWlInputVisible"
                ref="wlInputRef"
                v-model="newWlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.wlInputPlaceholder')"
                @keyup.enter="addWhitelistItem"
                @blur="addWhitelistItem"
              />
              <el-button v-else size="small" @click="openWlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" @click="openDirPicker('whitelist', 'local')">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseSelect') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.localPickerTip') }}</div>
          </el-form-item>
          <el-form-item v-if="editMode === 'blacklist'" :label="$t('backend.blacklistLabel')" prop="configData.edit_blacklist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as any).edit_blacklist"
                :key="'bl-local-' + idx"
                closable
                size="small"
                type="danger"
                @close="removeFromBlacklist(Number(idx))"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isBlInputVisible"
                ref="blInputRef"
                v-model="newBlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.blInputPlaceholder')"
                @keyup.enter="addBlacklistItem"
                @blur="addBlacklistItem"
              />
              <el-button v-else size="small" type="danger" plain @click="openBlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" type="danger" plain @click="openDirPicker('blacklist', 'local')">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseSelect') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.localPickerTip') }}</div>
          </el-form-item>

          <el-form-item label="Ignore Dirs" prop="configData.ignore_dirs">
            <el-select v-model="form.configData.ignore_dirs" multiple filterable allow-create default-first-option :placeholder="$t('backend.ignoreDirsPlaceholder')" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 通用配置 (仅 SSH) -->
        <template v-if="form.backendType === 'ssh'">
          <el-divider content-position="left">{{ $t('backend.commonConfig') }}</el-divider>

          <el-form-item label="Root Dir" prop="configData.root_dir">
            <el-input v-model="form.configData.root_dir" :placeholder="$t('backend.rootDirSshPlaceholder')" />
          </el-form-item>

          <el-divider content-position="left">{{ $t('backend.editPermission') }}</el-divider>

          <el-form-item :label="$t('backend.editMode')">
            <el-radio-group v-model="editMode" @change="onEditModeChange">
              <el-radio value="whitelist">{{ $t('backend.whitelistModeDir') }}</el-radio>
              <el-radio value="blacklist">{{ $t('backend.blacklistModeDir') }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="editMode === 'whitelist'" :label="$t('backend.whitelistLabel')" prop="configData.edit_whitelist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as SshConfigData).edit_whitelist"
                :key="'wl-' + idx"
                closable
                @close="removeWhitelistItem(idx)"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isWlInputVisible"
                ref="wlInputRef"
                v-model="newWlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.wlInputPlaceholder')"
                @keyup.enter="addWhitelistItem"
                @blur="addWhitelistItem"
              />
              <el-button v-else size="small" @click="openWlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" @click="openDirPicker('whitelist')" :disabled="!canBrowseSSH">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseSelect') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.sshPickerTip') }}</div>
          </el-form-item>

          <el-form-item v-if="editMode === 'blacklist'" :label="$t('backend.blacklistLabel')" prop="configData.edit_blacklist">
            <div class="path-picker-row">
              <el-tag
                v-for="(item, idx) in (form.configData as SshConfigData).edit_blacklist"
                :key="'bl-' + idx"
                closable
                @close="removeBlacklistItem(idx)"
                type="danger"
                class="path-tag"
              >{{ item }}</el-tag>
              <el-input
                v-if="isBlInputVisible"
                ref="blInputRef"
                v-model="newBlValue"
                size="small"
                class="tag-input-inline"
                :placeholder="$t('backend.blInputPlaceholder')"
                @keyup.enter="addBlacklistItem"
                @blur="addBlacklistItem"
              />
              <el-button v-else size="small" type="danger" plain @click="openBlInput">{{ $t('backend.addManual') }}</el-button>
              <el-button size="small" type="danger" plain @click="openDirPicker('blacklist')" :disabled="!canBrowseSSH">
                <el-icon><FolderOpened /></el-icon> {{ $t('backend.browseSelect') }}
              </el-button>
            </div>
            <div class="path-picker-tip">{{ $t('backend.sshPickerTip') }}</div>
          </el-form-item>

          <el-form-item label="Ignore Dirs" prop="configData.ignore_dirs">
            <el-select v-model="form.configData.ignore_dirs" multiple filterable allow-create default-first-option :placeholder="$t('backend.ignoreDirsPlaceholder')" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 工具配置 (SSH / API / Local) -->
        <template v-if="form.backendType === 'ssh' || form.backendType === 'api' || form.backendType === 'local'">
          <el-divider content-position="left">{{ $t('backend.toolConfig') }}</el-divider>
          <el-form-item>
            <template #label>
              <el-tooltip :content="$t('backend.executeTooltip')" placement="top">
                <span>{{ $t('backend.executeLabel') }} <span style="font-size: 11px; color: var(--el-text-color-secondary);">{{ $t('backend.executeSubLabel') }}</span></span>
              </el-tooltip>
            </template>
            <div class="tools-config-row">
              <span class="tools-config-label">{{ $t('backend.toolEnabled') }}</span>
              <el-switch v-model="form.tools_config!.execute.enabled" />
              <template v-if="form.tools_config!.execute.enabled">
                <span class="tools-config-label" style="margin-left: 16px;">{{ $t('backend.toolRequireReview') }}</span>
                <el-switch v-model="form.tools_config!.execute.require_review" />
              </template>
            </div>
            <div class="tools-config-tip">{{ $t('backend.toolExecuteTip') }}</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button
            v-if="form.backendType === 'ssh'"
            type="info"
            plain
            @click="handleTestConnection"
            :loading="isTesting"
          >
            <el-icon><Connection /></el-icon> {{ $t('backend.testConnection') }}
          </el-button>
          <div class="right-actions">
            <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
            <el-button type="primary" @click="submitForm" :loading="isSaving">{{ $t('common.action.confirm') }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 公钥展示弹窗 -->
    <el-dialog v-model="keyDialogVisible" :title="$t('backend.systemPublicKey')" width="500px">
      <div v-loading="!systemPublicKey" class="public-key-container">
        <p class="key-tip" v-html="$t('backend.publicKeyTip')"></p>
        <el-input v-model="systemPublicKey" type="textarea" :rows="6" readonly class="key-textarea" />
      </div>
      <template #footer>
        <el-button @click="keyDialogVisible = false">{{ $t('common.action.close') }}</el-button>
        <el-button type="primary" @click="copyPublicKey" :disabled="!systemPublicKey">
          {{ $t('common.action.copy') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 远程目录选择器弹窗 -->
    <el-dialog
      v-model="dirPickerVisible"
      :title="dirPickerMode === 'whitelist' ? $t('backend.dirPickerTitleWhitelist') : $t('backend.dirPickerTitleBlacklist')"
      width="580px"
      :close-on-click-modal="false"
      @open="onDirPickerOpen"
    >
      <div class="dir-picker-container">
        <div v-if="dirPickerError" class="dir-picker-error">
          <el-alert type="error" :closable="false" show-icon :title="dirPickerError" />
        </div>
        <!-- 面包屑导航 + 当前目录勾选 -->
        <div class="dir-picker-breadcrumb">
          <el-checkbox
            v-model="isCurrentDirChecked"
            :disabled="!currentRemoteDir || currentRemoteDir === '/'"
            class="crumb-checkbox"
          />
          <el-button link size="small" @click="navigateDir('/')" :disabled="currentRemoteDir === '/'">
            <el-icon><HomeFilled /></el-icon>
          </el-button>
          <template v-for="(part, idx) in breadcrumbParts" :key="idx">
            <span class="crumb-sep">/</span>
            <el-button link size="small" @click="navigateDir(part.remotePath)">{{ part.name }}</el-button>
          </template>
        </div>
        <!-- 提示 -->
        <div class="dir-picker-hint">
          {{ $t('backend.selectedCount', { count: tempSelectedPaths.size }) }}
          <el-button v-if="tempSelectedPaths.size > 0" link size="small" type="danger" @click="clearTempSelection">{{ $t('backend.clear') }}</el-button>
        </div>
        <!-- 目录列表 -->
        <div v-loading="isDirLoading" class="dir-picker-list">
          <div v-if="!isDirLoading && dirEntries.length === 0 && !dirPickerError" class="dir-empty">{{ $t('backend.dirEmpty') }}</div>
          <div
            v-for="entry in dirEntries"
            :key="entry.path"
            class="dir-entry"
            :class="{ 'is-checked': isTempSelected(entry) }"
          >
            <el-checkbox
              :model-value="isTempSelected(entry)"
              @change="toggleTempSelect(entry)"
              @click.stop
              class="dir-entry-checkbox"
            />
            <div class="dir-entry-body" @click="onDirEntryClick(entry)">
              <el-icon class="dir-entry-icon"><Folder /></el-icon>
              <span class="dir-entry-name">{{ entry.name }}</span>
              <el-icon class="dir-entry-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="dirPickerVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button
          type="primary"
          @click="confirmSelection"
          :disabled="tempSelectedPaths.size === 0"
        >
          {{ $t('backend.confirmSelection', { count: tempSelectedPaths.size }) }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 资源树目录选择器弹窗（Resource Backend） -->
    <el-dialog
      v-model="resPickerVisible"
      :title="resPickerMode === 'whitelist' ? $t('backend.resPickerTitleWhitelist') : $t('backend.resPickerTitleBlacklist')"
      width="580px"
      :close-on-click-modal="false"
      @open="onResPickerOpen"
    >
      <div class="dir-picker-container">
        <div class="dir-picker-hint">
          {{ $t('backend.selectedCount', { count: resPickerChecked.size }) }}
          <el-button v-if="resPickerChecked.size > 0" link size="small" type="danger" @click="resPickerChecked = new Set()">{{ $t('backend.clear') }}</el-button>
        </div>
        <div v-loading="isResTreeLoading" class="dir-picker-list">
          <div v-if="resFolderEntries.length === 0 && !isResTreeLoading" class="dir-empty">
            {{ $t('backend.resEmptyTip') }}
          </div>
          <div
            v-for="entry in resFolderEntries"
            :key="entry.vpath"
            class="dir-entry"
            :class="{ 'is-checked': resPickerChecked.has(entry.vpath) }"
            @click="toggleResPicker(entry.vpath)"
          >
            <el-checkbox
              :model-value="resPickerChecked.has(entry.vpath)"
              class="dir-entry-checkbox"
              @click.stop
            />
            <div class="dir-entry-body">
              <el-icon class="dir-entry-icon"><Folder /></el-icon>
              <span class="dir-entry-name">{{ entry.vpath }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="resPickerVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button
          type="primary"
          @click="confirmResPicker"
          :disabled="resPickerChecked.size === 0"
        >
          {{ $t('backend.confirmSelection', { count: resPickerChecked.size }) }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Key, Connection, View, Hide, FolderOpened, HomeFilled, Folder, ArrowRight } from '@element-plus/icons-vue';
import { useBackendStore } from '@/stores/backendStore';
import { useResourceStore } from '@/stores/resourceStore';
import { copyToClipboard } from '@/utils/clipboard';
import { getClientStatus, listDirectory } from '@/api/backendService';
import { getResourceDetails } from '@/api/resourceService';
import type { BackendConfig, BackendCreate, BackendType, SshConfigData, ApiConfigData, ResourceConfigData, LocalConfigData, SshTestRequest, SshLsEntry, UnifiedLsRequest } from '@/api/types/backendTypes';
import { isSshConfig, defaultToolsConfig } from '@/api/types/backendTypes';

const { t } = useI18n();
const backendStore = useBackendStore();
const resourceStore = useResourceStore();
const { backendList, isLoading, systemPublicKey } = storeToRefs(backendStore);
const { resourceTree } = storeToRefs(resourceStore);

const dialogVisible = ref(false);
const keyDialogVisible = ref(false);
const isEdit = ref(false);
const isSaving = ref(false);
const isTesting = ref(false);
const showApiKey = ref(false);
const currentEditId = ref<string | null>(null);

const formRef = ref<FormInstance>();
const clientStatusMap = ref<Record<string, { connected: boolean }>>({});
let statusPollTimer: ReturnType<typeof setInterval> | null = null;

// --- 远程目录选择器状态 ---
const VIRTUAL_WORKSPACE_ROOT = '/workspace';
const dirPickerVisible = ref(false);
const dirPickerMode = ref<'whitelist' | 'blacklist'>('whitelist');
const isDirLoading = ref(false);
const dirPickerError = ref('');
const dirEntries = ref<(SshLsEntry & { name: string })[]>([]);
const currentRemoteDir = ref('/');
const tempSelectedPaths = ref(new Set<string>());

// --- 编辑权限模式（白名单 / 黑名单互斥）---
const editMode = ref<'whitelist' | 'blacklist'>('whitelist');

function resolveEditMode(): 'whitelist' | 'blacklist' {
  const cd = form.configData as any;
  if (cd.edit_blacklist && cd.edit_blacklist.length > 0) return 'blacklist';
  return 'whitelist';
}

function onEditModeChange() {
  const cd = form.configData as any;
  if (editMode.value === 'whitelist') {
    cd.edit_blacklist = [];
  } else {
    cd.edit_whitelist = [];
  }
}

// --- 通用 tag 输入状态（API / Resource / Local 黑白名单）---
const isWlInputVisible = ref(false);
const newWlValue = ref('');
const isBlInputVisible = ref(false);
const newBlValue = ref('');
const wlInputRef = ref<any>(null);
const blInputRef = ref<any>(null);

function openWlInput() {
  isWlInputVisible.value = true;
  nextTick(() => wlInputRef.value?.focus());
}
function openBlInput() {
  isBlInputVisible.value = true;
  nextTick(() => blInputRef.value?.focus());
}

function addWhitelistItem() {
  const v = newWlValue.value.trim();
  if (v) {
    const arr = (form.configData as any).edit_whitelist || [];
    if (!arr.includes(v)) arr.push(v);
  }
  newWlValue.value = '';
  isWlInputVisible.value = false;
}

function addBlacklistItem() {
  const v = newBlValue.value.trim();
  if (v) {
    const arr = (form.configData as any).edit_blacklist || [];
    if (!arr.includes(v)) arr.push(v);
  }
  newBlValue.value = '';
  isBlInputVisible.value = false;
}

function removeFromWhitelist(idx: number) {
  (form.configData as any).edit_whitelist?.splice(idx, 1);
}

function removeFromBlacklist(idx: number) {
  (form.configData as any).edit_blacklist?.splice(idx, 1);
}

// 是否可以浏览 SSH 目录 — 需要填好 hostname + username
const canBrowseSSH = computed(() => {
  const cd = form.configData as SshConfigData;
  return !!(cd.hostname && cd.username);
});

// Local Backend 也可以浏览目录（本机文件系统）
const canBrowseLocal = computed(() => true);

// 当前目录选择器对应的 Backend 类型
const dirPickerBackendType = ref<'ssh' | 'local'>('ssh');

const currentVirtualPath = computed(() => {
  if (!currentRemoteDir.value || currentRemoteDir.value === '/') {
    return VIRTUAL_WORKSPACE_ROOT + '/';
  }
  const clean = currentRemoteDir.value.replace(/\/$/, '');
  return VIRTUAL_WORKSPACE_ROOT + clean + '/';
});

// 当前目录是否在临时勾选集合中
const isCurrentDirChecked = computed({
  get: () => tempSelectedPaths.value.has(currentVirtualPath.value),
  set: (val) => {
    const vp = currentVirtualPath.value;
    if (val) {
      tempSelectedPaths.value = new Set([...tempSelectedPaths.value, vp]);
    } else {
      const next = new Set(tempSelectedPaths.value);
      next.delete(vp);
      tempSelectedPaths.value = next;
    }
  },
});

const breadcrumbParts = computed(() => {
  if (!currentRemoteDir.value || currentRemoteDir.value === '/') return [];
  const parts = currentRemoteDir.value.split('/').filter(Boolean);
  const result: { name: string; remotePath: string }[] = [];
  let accum = '';
  for (const p of parts) {
    accum += '/' + p;
    result.push({ name: p, remotePath: accum + '/' });
  }
  return result;
});

function isTempSelected(entry: SshLsEntry & { name: string }): boolean {
  return tempSelectedPaths.value.has(remotePathToVirtual(entry.path));
}

function toggleTempSelect(entry: SshLsEntry & { name: string }) {
  const vp = remotePathToVirtual(entry.path);
  const next = new Set(tempSelectedPaths.value);
  if (next.has(vp)) {
    next.delete(vp);
  } else {
    next.add(vp);
  }
  tempSelectedPaths.value = next;
}

function clearTempSelection() {
  tempSelectedPaths.value = new Set();
}

function confirmSelection() {
  const cd = form.configData as any;
  const list = dirPickerMode.value === 'whitelist'
    ? cd.edit_whitelist!
    : cd.edit_blacklist!;
  if (!list) return;

  for (const vp of tempSelectedPaths.value) {
    if (!list.includes(vp)) {
      list.push(vp);
    }
  }
  dirPickerVisible.value = false;
}

function remotePathToVirtual(remotePath: string): string {
  let clean = remotePath.replace(/\/$/, '');
  return VIRTUAL_WORKSPACE_ROOT + clean + '/';
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function removeWhitelistItem(idx: number) {
  const arr = (form.configData as SshConfigData).edit_whitelist!;
  arr.splice(idx, 1);
}

function removeBlacklistItem(idx: number) {
  const arr = (form.configData as SshConfigData).edit_blacklist!;
  arr.splice(idx, 1);
}

function openDirPicker(mode: 'whitelist' | 'blacklist', backendType: 'ssh' | 'local' = 'ssh') {
  dirPickerMode.value = mode;
  dirPickerBackendType.value = backendType;
  dirPickerVisible.value = true;
}

async function onDirPickerOpen() {
  dirPickerError.value = '';
  tempSelectedPaths.value = new Set();
  currentRemoteDir.value = '/';
  await loadDirForPicker('/');
}

async function navigateDir(remotePath: string) {
  dirPickerError.value = '';
  currentRemoteDir.value = remotePath;
  await loadDirForPicker(remotePath);
}

async function loadDirForPicker(remotePath: string) {
  isDirLoading.value = true;
  dirPickerError.value = '';
  try {
    const isLocal = dirPickerBackendType.value === 'local';
    const cd = form.configData as any;
    const req: UnifiedLsRequest = {
      backend_type: isLocal ? 'local' : 'ssh',
      path: remotePath,
      root_dir: isLocal ? (cd.root_dir || '~') : (cd.root_dir || '/'),
      hostname: isLocal ? null : cd.hostname,
      port: isLocal ? undefined : (cd.port || 22),
      username: isLocal ? null : cd.username,
      password: isLocal ? null : (cd.password || null),
      backend_id: isEdit.value ? currentEditId.value : null,
    };
    const res = await listDirectory(req);
    if (res.success && res.entries) {
      dirEntries.value = res.entries
        .filter(e => e.is_dir || e.path.endsWith('/'))
        .map(e => ({ ...e, name: extractName(e.path) }))
        .sort((a, b) => a.name.localeCompare(b.name));
    } else {
      dirPickerError.value = res.message || t('backend.loadDirFailed');
      dirEntries.value = [];
    }
  } catch (err: any) {
    dirPickerError.value = err?.message || t('backend.loadDirFailed');
    dirEntries.value = [];
  } finally {
    isDirLoading.value = false;
  }
}

function extractName(path: string): string {
  const cleaned = path.replace(/\/$/, '');
  const idx = cleaned.lastIndexOf('/');
  return idx >= 0 ? cleaned.slice(idx + 1) : cleaned;
}

function onDirEntryClick(entry: SshLsEntry & { name: string }) {
  if (entry.is_dir) {
    navigateDir(entry.path);
  }
}

const sshDefaultConfig = (): SshConfigData => ({
  hostname: '',
  username: 'root',
  port: 22,
  password: null,
  root_dir: '/',
  edit_whitelist: [],
  edit_blacklist: [],
  ignore_dirs: ['.git', 'node_modules', 'build']
});

const apiDefaultConfig = (): ApiConfigData => ({
  api_key: '',
  edit_whitelist: [],
  edit_blacklist: [],
});

const resourceDefaultConfig = (): ResourceConfigData => ({
  resource_id: '',
  edit_whitelist: [],
  edit_blacklist: [],
  enable_version_editing: true,
});

const localDefaultConfig = (): LocalConfigData => ({
  root_dir: '~',
  edit_whitelist: [],
  edit_blacklist: [],
  ignore_dirs: ['.git', 'node_modules', '__pycache__']
});

const defaultForm = (type: BackendType = 'resource'): BackendCreate => ({
  name: '',
  description: '',
  backendType: type,
  configData: type === 'ssh' ? sshDefaultConfig() : type === 'api' ? apiDefaultConfig() : type === 'resource' ? resourceDefaultConfig() : localDefaultConfig(),
  tools_config: defaultToolsConfig()
});

// 名称校验：与后端 validate_path_safe_name 一致（黑名单策略）
const NAME_UNSAFE_RE = /[\/\\\x00-\x1f\x7f]/;
const RESERVED_NAMES = new Set(['skills', 'memories', 'state', 'root', 'tmp', 'temp', 'workspace', 'this_chat_tmp', '.mambo']);

function validateName(_rule: any, value: string, callback: (error?: Error) => void) {
  if (!value) return callback(new Error(t('backend.nameRequired')));
  if (NAME_UNSAFE_RE.test(value)) return callback(new Error(t('backend.nameUnsafe')));
  if (value === '.' || value === '..') return callback(new Error(t('backend.nameDot')));
  if (RESERVED_NAMES.has(value.toLowerCase())) return callback(new Error(t('backend.nameReserved', { name: value })));
  callback();
}

const nameRules = computed(() => [
  { required: true, message: t('backend.nameRequired'), trigger: 'blur' },
  { validator: validateName, trigger: 'blur' },
]);

const form = reactive<BackendCreate>(defaultForm('resource'));

const sshRules = computed<FormRules>(() => ({
  name: nameRules.value,
  'configData.hostname': [{ required: true, message: t('backend.hostRequired'), trigger: 'blur' }],
  'configData.username': [{ required: true, message: t('backend.usernameRequired'), trigger: 'blur' }]
}));

const apiRules = computed<FormRules>(() => ({
  name: nameRules.value,
  'configData.api_key': [{ required: true, message: t('backend.apiKeyRequired'), trigger: 'blur' }]
}));

const resourceRules = computed<FormRules>(() => ({
  name: nameRules.value,
  'configData.resource_id': [{ required: true, message: t('backend.resourceIdRequired'), trigger: 'change' }]
}));

const localRules = computed<FormRules>(() => ({
  name: nameRules.value
}));

const currentRules = computed(() => {
  if (form.backendType === 'ssh') return sshRules.value;
  if (form.backendType === 'api') return apiRules.value;
  if (form.backendType === 'resource') return resourceRules.value;
  return localRules.value;
});

const handleTypeChange = (type: BackendType) => {
  const newForm = defaultForm(type);
  newForm.name = form.name;
  newForm.description = form.description;
  Object.assign(form, newForm);
  editMode.value = 'whitelist';
  formRef.value?.clearValidate();
};

// --- 资源文件夹选择器逻辑 ---
const isResourceFoldersLoading = ref(false);

// 通过资源 id 解析出虚拟路径（如 /目录1/目录2），基于已加载的资源列表向上回溯
function resolveResourcePath(resourceId: string): string {
  if (!resourceId) return '';
  const itemMap = new Map(resourceStore.resources.map(r => [r.id, r]));
  const names: string[] = [];
  const seen = new Set<string>();
  let current = itemMap.get(resourceId);
  while (current) {
    if (seen.has(current.id)) break;
    seen.add(current.id);
    names.unshift(current.name);
    if (!current.parentId || current.parentId === 'root') break;
    current = itemMap.get(current.parentId);
  }
  return names.length > 0 ? '/' + names.join('/') : '';
}

// [新增] 路径解析缓存：资源树未加载到对应节点时，按 ID 向 API 回源拼路径，
// 避免依赖"必须先去资源页面展开过"才能显示路径
const resolvedResourcePaths = ref(new Map<string, string>());
const resolvingResourcePaths = ref(new Set<string>());

async function resolveResourcePathAsync(resourceId: string): Promise<void> {
  if (!resourceId) return;
  if (resolvedResourcePaths.value.has(resourceId)) return;
  if (resolvingResourcePaths.value.has(resourceId)) return;
  resolvingResourcePaths.value.add(resourceId);
  try {
    let path = resolveResourcePath(resourceId);
    if (!path) {
      const names: string[] = [];
      const seen = new Set<string>();
      let currentId = resourceId;
      while (currentId && !seen.has(currentId)) {
        seen.add(currentId);
        const detail = await getResourceDetails(currentId).catch(() => null);
        if (!detail) break;
        names.unshift(detail.name);
        if (!detail.parentId || detail.parentId === 'root') break;
        currentId = detail.parentId;
      }
      path = names.length > 0 ? '/' + names.join('/') : '';
    }
    resolvedResourcePaths.value.set(resourceId, path);
  } finally {
    resolvingResourcePaths.value.delete(resourceId);
  }
}

// backend 列表就绪/变化时，预解析 resource 类型 backend 的资源路径
watch(backendList, (list) => {
  list
    .filter(b => b.backendType === 'resource' && b.configData?.resource_id)
    .forEach(b => resolveResourcePathAsync(b.configData.resource_id));
}, { immediate: true });

function collectFolders(nodes: any[]): { id: string; name: string; path: string }[] {
  const folders: { id: string; name: string; path: string }[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      folders.push({ id: node.id, name: node.name, path: resolveResourcePath(node.id) });
    }
    if (node.children && node.children.length > 0) {
      folders.push(...collectFolders(node.children));
    }
  }
  return folders;
}

const resourceFolderOptions = computed(() => {
  return collectFolders(resourceTree.value);
});

async function onResourceFolderDropdownVisible(visible: boolean) {
  if (visible && resourceTree.value.length === 0) {
    isResourceFoldersLoading.value = true;
    try {
      await resourceStore.initializeList();
    } finally {
      isResourceFoldersLoading.value = false;
    }
  }
}

// --- 资源树目录选择器（Resource Backend 浏览选择）---
interface ResFolderEntry {
  vpath: string;
}

const resPickerVisible = ref(false);
const resPickerMode = ref<'whitelist' | 'blacklist'>('whitelist');
const resPickerChecked = ref(new Set<string>());
const isResTreeLoading = ref(false);

const resFolderEntries = computed<ResFolderEntry[]>(() => {
  const entries: ResFolderEntry[] = [];
  const seen = new Set<string>();
  function walk(nodes: any[], parentVpath: string) {
    for (const node of nodes) {
      if (node.itemType === 'folder') {
        const vpath = parentVpath + node.name + '/';
        if (!seen.has(vpath)) {
          seen.add(vpath);
          entries.push({ vpath });
        }
        if (node.children && node.children.length > 0) {
          walk(node.children, vpath);
        }
      }
    }
  }
  walk(resourceTree.value, '/workspace/');
  return entries;
});

function openResPicker(mode: 'whitelist' | 'blacklist') {
  resPickerMode.value = mode;
  resPickerVisible.value = true;
}

async function onResPickerOpen() {
  resPickerChecked.value = new Set();
  if (resourceTree.value.length === 0) {
    isResTreeLoading.value = true;
    try {
      await resourceStore.initializeList();
    } finally {
      isResTreeLoading.value = false;
    }
  }
}

function toggleResPicker(vpath: string) {
  const next = new Set(resPickerChecked.value);
  if (next.has(vpath)) {
    next.delete(vpath);
  } else {
    next.add(vpath);
  }
  resPickerChecked.value = next;
}

function confirmResPicker() {
  const target = resPickerMode.value === 'whitelist'
    ? (form.configData as any).edit_whitelist
    : (form.configData as any).edit_blacklist;
  if (!target) return;
  for (const vp of resPickerChecked.value) {
    if (!target.includes(vp)) {
      target.push(vp);
    }
  }
  resPickerVisible.value = false;
}

function maskKey(key?: string | null): string {
  if (!key) return '***';
  if (key.length <= 8) return '********';
  return key.slice(0, 4) + '****' + key.slice(-4);
}

async function fetchClientStatuses() {
  for (const b of backendList.value) {
    if (b.backendType === 'api') {
      try {
        const status = await getClientStatus(b.id);
        clientStatusMap.value[b.id] = status;
      } catch {
        clientStatusMap.value[b.id] = { connected: false };
      }
    }
  }
}

onMounted(() => {
  backendStore.fetchBackends();
  resourceStore.initializeList();
  statusPollTimer = setInterval(fetchClientStatuses, 15000);
});

onUnmounted(() => {
  if (statusPollTimer) clearInterval(statusPollTimer);
});

const handleCreate = () => {
  isEdit.value = false;
  currentEditId.value = null;
  showApiKey.value = false;
  Object.assign(form, defaultForm('resource'));
  editMode.value = 'whitelist';
  dialogVisible.value = true;
  formRef.value?.clearValidate();
};

const handleEdit = (row: BackendConfig) => {
  isEdit.value = true;
  currentEditId.value = row.id;
  showApiKey.value = false;

  const type = row.backendType;
  const rawData = JSON.parse(JSON.stringify(row.configData)) as Record<string, any>;
  // Normalize enable_version_editing: default to true when undefined/null
  if (rawData.enable_version_editing == null) {
    rawData.enable_version_editing = true;
  }
  // Enforce mutual exclusion for legacy data: if both are set, keep only whitelist
  const wl = rawData.edit_whitelist || [];
  const bl = rawData.edit_blacklist || [];
  if (wl.length > 0 && bl.length > 0) {
    // Both set — clear blacklist (whitelist takes priority)
    rawData.edit_blacklist = [];
  }

  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    backendType: type,
    configData: {
      ...rawData,
      edit_whitelist: rawData.edit_whitelist || [],
      edit_blacklist: rawData.edit_blacklist || [],
      ignore_dirs: rawData.ignore_dirs || [],
    },
    tools_config: row.tools_config ? JSON.parse(JSON.stringify(row.tools_config)) : defaultToolsConfig(),
  });
  editMode.value = resolveEditMode();
  dialogVisible.value = true;
  formRef.value?.clearValidate();
};

const handleDelete = async (id: string) => {
  try {
    await backendStore.removeBackend(id);
    ElMessage.success(t('common.msg.deleteSuccess'));
  } catch (error) {
    ElMessage.error(t('backend.deleteFailed'));
  }
};

const handleDuplicate = async (id: string) => {
  try {
    await backendStore.duplicateBackendItem(id);
    ElMessage.success(t('backend.duplicateSuccess'));
  } catch (error) {
    ElMessage.error(t('backend.duplicateFailed'));
  }
};

const handleTestConnection = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isTesting.value = true;
      try {
        const testData: SshTestRequest = {
          backend_id: isEdit.value ? currentEditId.value : null,
          configData: {
            ...form.configData,
            edit_whitelist: form.configData.edit_whitelist?.length === 0 ? null : form.configData.edit_whitelist,
            edit_blacklist: form.configData.edit_blacklist?.length === 0 ? null : form.configData.edit_blacklist,
            ignore_dirs: form.configData.ignore_dirs?.length === 0 ? null : form.configData.ignore_dirs,
            password: form.configData.password || null
          }
        };
        const res = await backendStore.testConnection(testData);
        if (res.success) {
          ElMessage.success(t('backend.connectionSuccess'));
        } else {
          ElMessage.error(t('backend.connectionFailed'));
        }
      } catch (error: any) {
        ElMessage.error(error.message || t('backend.connectionError'));
      } finally {
        isTesting.value = false;
      }
    }
  });
};

const submitForm = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSaving.value = true;
      try {
        const submitData: BackendCreate = JSON.parse(JSON.stringify(form));
        const cd = submitData.configData as any;

        if (submitData.backendType === 'ssh') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
          if (cd.ignore_dirs?.length === 0) cd.ignore_dirs = null;
          if (!cd.password) cd.password = null;
        } else if (submitData.backendType === 'api') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
          if (!cd.api_key) cd.api_key = null;
        } else if (submitData.backendType === 'resource') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
        } else if (submitData.backendType === 'local') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
          if (cd.ignore_dirs?.length === 0) cd.ignore_dirs = null;
          if (!cd.root_dir || cd.root_dir === '~') cd.root_dir = '~';
        }

        if (isEdit.value && currentEditId.value) {
          await backendStore.updateExistingBackend(currentEditId.value, submitData);
          ElMessage.success(t('common.msg.updateSuccess'));
        } else {
          await backendStore.createNewBackend(submitData);
          ElMessage.success(t('common.msg.createSuccess'));
        }
        dialogVisible.value = false;
      } catch (error) {
        ElMessage.error(isEdit.value ? t('backend.updateFailed') : t('common.msg.createFailed'));
      } finally {
        isSaving.value = false;
      }
    }
  });
};

const handleShowPublicKey = async () => {
  keyDialogVisible.value = true;
  if (!systemPublicKey.value) {
    await backendStore.fetchPublicKey();
  }
};

const copyPublicKey = async () => {
  if (systemPublicKey.value) {
    await copyToClipboard(systemPublicKey.value);
    ElMessage.success(t('common.msg.copySuccess'));
  }
};
</script>

<style scoped>
.backend-manager-panel {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.toolbar {
  margin-bottom: 16px;
  display: flex;
  gap: 12px;
}

.backend-table {
  flex-grow: 1;
}

.api-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.api-id {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.status-tag {
  margin-left: auto;
}

.api-tip {
  margin-bottom: 16px;
}

.local-warning {
  margin-bottom: 16px;
}

.public-key-container {
  min-height: 150px;
}

.key-tip {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.key-textarea {
  font-family: monospace;
  font-size: 12px;
}

.dialog-footer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.right-actions {
  display: flex;
  gap: 12px;
}

.tools-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tools-config-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.tools-config-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 路径选择器 */
.path-picker-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 32px;
}

.path-tag {
  margin-bottom: 2px;
}

.tag-input-inline {
  width: 220px;
  min-width: 160px;
}

.path-picker-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 目录选择器弹窗 */
.dir-picker-container {
  min-height: 300px;
  display: flex;
  flex-direction: column;
}

.dir-picker-error {
  margin-bottom: 12px;
}

.dir-picker-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  margin-bottom: 8px;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
}

.crumb-checkbox {
  margin-right: 6px;
  height: auto;
}

.crumb-sep {
  color: var(--el-text-color-placeholder);
  margin: 0 2px;
}

.dir-picker-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 0 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.dir-picker-list {
  flex: 1;
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
}

.dir-empty {
  padding: 40px;
  text-align: center;
  color: var(--el-text-color-placeholder);
}

.dir-entry {
  display: flex;
  align-items: center;
  gap: 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  transition: background-color 0.15s;
}

.dir-entry-checkbox {
  padding: 8px 0 8px 12px;
  margin: 0;
  flex-shrink: 0;
  height: auto;
}

.dir-entry.is-checked {
  background: var(--el-color-primary-light-9);
}

.dir-entry-body {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding: 8px 12px;
  cursor: pointer;
  min-width: 0;
}

.dir-entry-body:hover {
  background: var(--el-fill-color-light);
}

.dir-entry.is-checked .dir-entry-body:hover {
  background: var(--el-color-primary-light-8);
}

.dir-entry-icon {
  color: var(--el-color-warning);
  flex-shrink: 0;
}

.dir-entry-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dir-entry-size {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

.dir-entry-arrow {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
</style>
