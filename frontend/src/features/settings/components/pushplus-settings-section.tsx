import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, CircleDashedIcon, SaveIcon } from "lucide-react";
import { toast } from "sonner";

import { QueryErrorState, QueryLoadingState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SecretInput } from "@/components/ui/secret-input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ConfigurationConflictDialog } from "@/features/settings/components/configuration-conflict-dialog";
import { ConfigurationReloadNotice } from "@/features/settings/components/configuration-reload-notice";
import { getSettings, updateSettings } from "@/lib/api";
import { requireRevision } from "@/lib/configuration-revision";
import { getErrorMessage } from "@/lib/format";
import { isApiConflictError, type ApiConflictError } from "@/lib/openapi-client";
import type { PushplusChannel } from "@/lib/api-types";
import { cn } from "@/lib/utils";

const SETTINGS_QUERY_KEY = ["settings"] as const;

function PushplusStatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-5 gap-1 rounded-sm px-1.5 text-[11px] leading-none font-medium",
        enabled
          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
          : "border-amber-500/30 bg-amber-500/10 text-amber-700",
      )}
    >
      {enabled ? <CheckCircle2Icon className="size-3" /> : <CircleDashedIcon className="size-3" />}
      {enabled ? "已开启" : "已关闭"}
    </Badge>
  );
}

/** Configure PushPlus trade summaries. */
export function PushplusSettingsPage() {
  const [reloadVersion, setReloadVersion] = useState(0);
  const settingsQuery = useQuery({ queryKey: SETTINGS_QUERY_KEY, queryFn: getSettings });
  const settings = settingsQuery.data;

  if (settingsQuery.isLoading) {
    return <QueryLoadingState label="正在加载推送设置…" />;
  }
  if (settingsQuery.isError && !settings) {
    return (
      <QueryErrorState
        title="推送设置加载失败"
        error={settingsQuery.error}
        onRetry={() => void settingsQuery.refetch()}
      />
    );
  }
  if (!settings) return null;

  return (
    <PushplusSettingsForm
      key={`${settings.revision}-${reloadVersion}`}
      settings={settings}
      refreshError={settingsQuery.error}
      onReload={async () => {
        const result = await settingsQuery.refetch();
        if (result.isError || result.data === undefined) return false;
        setReloadVersion((version) => version + 1);
        return true;
      }}
    />
  );
}

function PushplusSettingsForm({
  settings,
  refreshError,
  onReload,
}: {
  settings: Awaited<ReturnType<typeof getSettings>>;
  refreshError: Error | null;
  onReload: () => Promise<boolean>;
}) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(settings.pushplus.enabled);
  const [channel, setChannel] = useState<PushplusChannel>(settings.pushplus.channel);
  const [tokenDraft, setTokenDraft] = useState("");
  const [webhookOptionDraft, setWebhookOptionDraft] = useState("");
  const [conflict, setConflict] = useState<ApiConflictError | null>(null);
  const [needsReload, setNeedsReload] = useState(false);

  const reportWriteError = (error: unknown) => {
    if (isApiConflictError(error)) {
      setConflict(error);
      setNeedsReload(true);
      return;
    }
    toast.error(getErrorMessage(error));
  };

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(SETTINGS_QUERY_KEY, updated);
      setTokenDraft("");
      setWebhookOptionDraft("");
      toast.success("推送设置已保存");
    },
    onError: reportWriteError,
  });

  const disabled = updateMutation.isPending || needsReload;
  const saveSettings = () => {
    updateMutation.mutate({
      expected_revision: requireRevision(settings.revision, "推送设置"),
      pushplus: {
        enabled,
        channel,
        ...(tokenDraft.trim() ? { token: tokenDraft.trim() } : {}),
        ...(channel === "webhook" && webhookOptionDraft.trim()
          ? { webhook_option: webhookOptionDraft.trim() }
          : {}),
      },
    });
  };

  const reloadServerConfiguration = async () => {
    if (!(await onReload())) return;
    setTokenDraft("");
    setWebhookOptionDraft("");
    setNeedsReload(false);
    setConflict(null);
  };

  return (
    <section className="w-full max-w-[986px]" aria-label="推送设置内容">
      <div className="space-y-4">
        {refreshError ? (
          <p className="text-destructive text-sm">后台刷新失败：{getErrorMessage(refreshError)}</p>
        ) : null}
        <ConfigurationReloadNotice visible={needsReload} onReload={reloadServerConfiguration} />
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            saveSettings();
          }}
        >
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="pushplus-enabled" className="text-sm font-medium">
              PushPlus 推送
            </label>
            <Switch
              id="pushplus-enabled"
              checked={enabled}
              disabled={disabled}
              onCheckedChange={setEnabled}
              aria-label="开启 PushPlus 推送"
            />
            <PushplusStatusBadge enabled={enabled} />
          </div>
          <p className="text-muted-foreground text-sm leading-6">
            开启后，仅在模拟买入或卖出成功时发送股票名称、代码、方向、数量和交易总额。
          </p>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="pushplus-token" className="text-sm font-medium">
                PushPlus Token
              </label>
              <SecretInput
                id="pushplus-token"
                value={tokenDraft}
                disabled={disabled}
                onChange={(event) => setTokenDraft(event.target.value)}
                placeholder={
                  settings.pushplus.token_configured ? "留空保持当前 Token" : "输入 PushPlus Token"
                }
                autoComplete="off"
              />
              {settings.pushplus.token_configured && settings.pushplus.token_last_four ? (
                <p className="text-muted-foreground text-xs">当前 Token 尾号 {settings.pushplus.token_last_four}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="pushplus-channel" className="text-sm font-medium">
                发送渠道
              </label>
              <Select
                value={channel}
                onValueChange={(value) => setChannel(value as PushplusChannel)}
                disabled={disabled}
              >
                <SelectTrigger id="pushplus-channel" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="wechat">微信（wechat）</SelectItem>
                  <SelectItem value="webhook">Webhook（webhook）</SelectItem>
                  <SelectItem value="cmcc">新消息 ClawBot（cmcc）</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {channel === "webhook" ? (
              <div className="space-y-2 md:col-span-2">
                <label htmlFor="pushplus-webhook-option" className="text-sm font-medium">
                  Webhook 渠道编码
                </label>
                <SecretInput
                  id="pushplus-webhook-option"
                  value={webhookOptionDraft}
                  disabled={disabled}
                  onChange={(event) => setWebhookOptionDraft(event.target.value)}
                  placeholder={
                    settings.pushplus.webhook_option_configured
                      ? "留空保持当前渠道编码"
                      : "输入 PushPlus 渠道编码"
                  }
                  autoComplete="off"
                />
                {settings.pushplus.webhook_option_configured &&
                settings.pushplus.webhook_option_last_four ? (
                  <p className="text-muted-foreground text-xs">
                    当前渠道编码尾号 {settings.pushplus.webhook_option_last_four}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          <Button type="submit" disabled={disabled}>
            <SaveIcon className="size-4" />
            保存推送设置
          </Button>
        </form>
      </div>

      <ConfigurationConflictDialog
        conflict={conflict}
        onKeepLocal={() => setConflict(null)}
        onReload={reloadServerConfiguration}
      />
    </section>
  );
}
