import { describe, expect, it } from "vitest";
import { PRODUCT_PROVIDER_LABEL, productProviderLabel } from "@/lib/format/labels";

/**
 * 백엔드 `app/clients/public_data_products.py` 의 `PROVIDER_NAME` 이다.
 * 이 문자열이 바뀌면 화면 기관명이 조용히 원문 식별자로 떨어지므로 고정한다.
 */
const BACKEND_PROVIDER_NAME = "financial_services_commission";

describe("productProviderLabel", () => {
  it("공식 상품 provider 를 기관명으로 바꾼다", () => {
    expect(productProviderLabel(BACKEND_PROVIDER_NAME)).toBe("금융위원회");
  });

  it("백엔드 PROVIDER_NAME 이 매핑에 들어 있다", () => {
    expect(PRODUCT_PROVIDER_LABEL).toHaveProperty(BACKEND_PROVIDER_NAME);
  });

  it("모르는 provider 는 기관명을 지어내지 않고 원문을 그대로 둔다", () => {
    expect(productProviderLabel("some_unregistered_provider")).toBe(
      "some_unregistered_provider",
    );
  });

  it("빈 문자열도 지어내지 않는다", () => {
    expect(productProviderLabel("")).toBe("");
  });
});
