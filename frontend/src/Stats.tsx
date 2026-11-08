import Icon from "./Icon";
import type { IconName } from "./Icon";

export interface StatItem {
  label: string;
  value: number;
  detail: string;
  icon: IconName;
  tone?: "teal" | "blue" | "amber" | "violet";
}
export default function Stats({ items }: { items: StatItem[] }) {
  return <div className="stats-grid">{items.map((item) => <div className="stat-card" key={item.label}>
    <div><span className="stat-label">{item.label}</span><strong className="stat-number">{item.value.toLocaleString("vi-VN")}</strong><small>{item.detail}</small></div>
    <span className={`stat-icon tone-${item.tone ?? "teal"}`}><Icon name={item.icon} size={22} /></span>
  </div>)}</div>;
}
