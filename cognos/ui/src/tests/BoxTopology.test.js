import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/extend-expect";
import "@testing-library/jest-dom";
import BoxTopology from "../components/BoxTopology";

test("renders BoxTopology component", () => {
  render(<BoxTopology />);
});

test("handles previous and next button clicks correctly", () => {
   render(<BoxTopology />);

  expect(screen.getByTestId("prev-button")).toBeInTheDocument();
  expect(screen.getByTestId("next-button")).toBeInTheDocument();
});

describe("BoxTopology", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });
  test("fetches hostToDeviceMapping data and renders components correctly", async () => {
    const mockData = [
      { host: "Host1", devices: ["D1", "D3", "D6"] },
      { host: "Host2", devices: ["D4"] },
      { host: "Host3", devices: ["D5"] },
    ];

    global.fetch = jest.fn().mockResolvedValueOnce({
      json: () => Promise.resolve(mockData),
    });

    /**
     * @todo Implement detection for devices/hosts displayed in topology
     */
  });
});
