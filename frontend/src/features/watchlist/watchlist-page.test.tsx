import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { AppSidebar } from "@/components/app-sidebar";
import { SidebarProvider } from "@/components/ui/sidebar";

import { WatchlistPage } from "./watchlist-page";

const api = vi.hoisted(() => ({ getWatchlist: vi.fn() }));
vi.mock("@/lib/api", () => api);

const watchlist = {
  columns: [
    { key: "SECURITY_CODE", title: "股票代码" },
    { key: "SECURITY_NAME", title: "股票名称" },
    { key: "最新价", title: "最新价" },
  ],
  items: [
    { SECURITY_CODE: "000001", SECURITY_NAME: "平安银行", 最新价: "10.5" },
    { SECURITY_CODE: "600519", SECURITY_NAME: "贵州茅台", 最新价: null },
  ],
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const rendered = render(
    <QueryClientProvider client={client}>
      <WatchlistPage />
    </QueryClientProvider>,
  );
  return { ...rendered, client };
}

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("自选股票展示", () => {
  it("provides an active watchlist entry in the left sidebar", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
    render(
      <MemoryRouter initialEntries={["/watchlist"]}>
        <SidebarProvider>
          <AppSidebar />
        </SidebarProvider>
      </MemoryRouter>,
    );
    const entry = screen.getByRole("link", { name: "自选股票" });
    expect(entry).toHaveAttribute("href", "/watchlist");
    expect(entry).toHaveAttribute("aria-current", "page");
  });

  it("shows every stock and upstream field without manual controls", async () => {
    api.getWatchlist.mockResolvedValue(watchlist);
    renderPage();
    const table = await screen.findByRole("table", { name: "自选股票列表" });
    expect(within(table).getByText("000001")).toBeInTheDocument();
    expect(within(table).getByText("平安银行")).toBeInTheDocument();
    expect(within(table).getByText("贵州茅台")).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "最新价" })).toBeInTheDocument();
    expect(within(table).getByText("10.5")).toBeInTheDocument();
    expect(within(table).getByText("--")).toBeInTheDocument();
    expect(screen.getByText("共 2 只")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("loads and displays an empty account without an add-stock action", async () => {
    let resolve: (value: typeof watchlist) => void = () => {};
    api.getWatchlist.mockReturnValue(
      new Promise<typeof watchlist>((done) => {
        resolve = done;
      }),
    );
    renderPage();
    expect(screen.getByText("正在加载自选股票…")).toBeInTheDocument();
    resolve({ columns: [], items: [] });
    expect(await screen.findByText("暂无自选股票")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("reports failures without presenting them as an empty account", async () => {
    api.getWatchlist.mockRejectedValue(new Error("妙想接口暂时不可用"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("妙想接口暂时不可用");
    expect(screen.queryByText("暂无自选股票")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps displayed stocks on a background refresh error and recovers on the next sync", async () => {
    api.getWatchlist.mockResolvedValue(watchlist);
    const { client, unmount } = renderPage();
    await screen.findByRole("table");
    api.getWatchlist.mockRejectedValue(new Error("自动同步失败"));
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["account", "watchlist"] });
    });
    await waitFor(() => expect(api.getWatchlist).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("alert")).toHaveTextContent("自动同步失败");
    expect(screen.getByText("平安银行")).toBeInTheDocument();
    api.getWatchlist.mockResolvedValue({ ...watchlist, items: [watchlist.items[1]] });
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["account", "watchlist"] });
    });
    await waitFor(() => expect(screen.getByText("共 1 只")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("平安银行")).not.toBeInTheDocument();
    unmount();
    client.clear();
  });
});
