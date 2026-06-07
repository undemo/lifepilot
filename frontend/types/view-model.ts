export type TimelineViewItem = {
  stepId: string;
  order: number;
  title: string;
  description?: string;
  timeLabel: string;
  tags: string[];
  routeLabel?: string;
  bookingLabel?: string;
  note?: string;
};

export type ToolTraceViewItem = {
  id: string;
  label: string;
  status?: string;
};
