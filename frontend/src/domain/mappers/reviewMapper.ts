import { HumanReviewItem } from "../models/HumanReviewItem";
import type { components } from "../../api/generated/schema";

type HumanReviewDto = components["schemas"]["HumanReviewSchema"];

export function toHumanReviewItemDomain(dto: HumanReviewDto): HumanReviewItem {
  return new HumanReviewItem(
    dto.review_item_id,
    dto.camera_id,
    dto.track_id,
    dto.reason,
    dto.status,
  );
}
