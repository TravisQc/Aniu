import { useQuery } from "@tanstack/react-query";
import { StarIcon } from "lucide-react";

import { QueryLoadingState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getWatchlist } from "@/lib/api";
import { getErrorMessage } from "@/lib/format";

export function WatchlistPage() {
  const watchlist = useQuery({
    queryKey: ["account", "watchlist"],
    queryFn: getWatchlist,
    refetchInterval: 60_000,
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <StarIcon className="size-4" aria-hidden="true" />
            自选股票
          </CardTitle>
          {watchlist.data ? (
            <Badge variant="secondary">共 {watchlist.data.items.length} 只</Badge>
          ) : null}
        </div>
        <CardDescription>自动同步东方财富账户的自选股票，仅供查看。</CardDescription>
      </CardHeader>
      <CardContent>
        {watchlist.isPending ? <QueryLoadingState label="正在加载自选股票…" /> : null}
        {watchlist.isError ? (
          <div
            role="alert"
            className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border p-4 text-sm"
          >
            <p className="font-medium">自选股票加载失败</p>
            <p className="mt-1">{getErrorMessage(watchlist.error)}</p>
            <p className="text-muted-foreground mt-1">稍后将自动重试。</p>
          </div>
        ) : null}
        {watchlist.data?.items.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <StarIcon aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle>暂无自选股票</EmptyTitle>
              <EmptyDescription>账户中的自选股票将在这里自动展示。</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
        {watchlist.data && watchlist.data.items.length > 0 ? (
          <Table aria-label="自选股票列表">
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">序号</TableHead>
                {watchlist.data.columns.map((column) => (
                  <TableHead key={column.key}>{column.title}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {watchlist.data.items.map((item, index) => (
                <TableRow key={index}>
                  <TableCell className="text-muted-foreground tabular-nums">{index + 1}</TableCell>
                  {watchlist.data.columns.map((column) => (
                    <TableCell key={column.key} className="tabular-nums">
                      {item[column.key] ?? "--"}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}
