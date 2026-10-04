import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PushplusSettingsPage } from "./pushplus-settings-section";

const api = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

const settings = {
  mx: { api_key_configured: false, api_key_last_four: null },
  prompt_profile: {
    schema: "aniu.prompt-profile.v3",
    name: "默认",
    description: "",
    global_prompt: "",
    run_prompt: "",
    summary_prompt: "",
    dream_prompt: "",
  },
  stage_settings: [],
  dream_schedule_time: "00:30",
  pushplus: {
    enabled: false,
    channel: "wechat" as const,
    token_configured: false,
    token_last_four: null,
    webhook_option_configured: false,
    webhook_option_last_four: null,
  },
  revision: 4,
  created_at: "2026-08-03T08:00:00Z",
  updated_at: "2026-08-03T08:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PushplusSettingsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("PushplusSettingsPage", () => {
  it("shows the disabled default and saves the selected channel configuration", async () => {
    const user = userEvent.setup();
    api.getSettings.mockResolvedValue(settings);
    api.updateSettings.mockResolvedValue({ ...settings, revision: 5 });

    renderPage();

    expect(await screen.findByRole("region", { name: "推送设置内容" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "开启 PushPlus 推送" })).not.toBeChecked();

    await user.click(screen.getByRole("switch", { name: "开启 PushPlus 推送" }));
    await user.type(screen.getByLabelText("PushPlus Token"), "pushplus-token");
    await user.click(screen.getByRole("button", { name: "保存推送设置" }));

    await waitFor(() => {
      expect(api.updateSettings.mock.calls[0]?.[0]).toEqual({
        expected_revision: 4,
        pushplus: {
          enabled: true,
          channel: "wechat",
          token: "pushplus-token",
        },
      });
    });
  });

  it("shows webhook option only for the webhook channel", async () => {
    const user = userEvent.setup();
    api.getSettings.mockResolvedValue(settings);
    renderPage();

    expect(await screen.findByRole("region", { name: "推送设置内容" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Webhook 渠道编码")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "发送渠道" }));
    await user.click(screen.getByRole("option", { name: "Webhook（webhook）" }));

    expect(screen.getByLabelText("Webhook 渠道编码")).toBeInTheDocument();
  });
});
