import React from "react";
import { render, screen } from "@testing-library/react";
import '@testing-library/jest-dom';

import {
    LoadingSpinner,
    DeviceCountCard,
    CapacityCard,
    BandwidthCard,
    VIEW_MODES
} from "./dashboard-utils";


// Mock Chart because Google Charts causes DOM errors
jest.mock("react-google-charts", () => ({
    Chart: () => <div data-testid="mock-chart"></div>
}));

// ----------- LoadingSpinner -----------
describe("LoadingSpinner", () => {

    test("applies height", () => {
        const { container } = render(<LoadingSpinner height={200} />);
        expect(container.firstChild).toHaveStyle({ height: "200px" });
    });
});

// ----------- DeviceCountCard -----------
describe("DeviceCountCard", () => {
    test("displays host and device counts", () => {
        render(<DeviceCountCard hostsCount={5} devicesCount={10} isLoading={false} />);
        expect(screen.getByText("5")).toBeInTheDocument();
        expect(screen.getByText("10")).toBeInTheDocument();
    });

    test("defaults to zero when null", () => {
        render(<DeviceCountCard isLoading={false} />);
        expect(screen.getAllByText("0").length).toBeGreaterThan(0);
    });
});

// ----------- CapacityCard -----------
describe("CapacityCard", () => {
    const capacityData = {
        used_capacity: 2048,
        total_capacity: 4096,
        used_capacity_percentage: 50,
    };

    const memData = [
        ["Memtype", "Capacity Used"],
        ["DRAM", 2000],
        ["CXL", 1000],
    ];

    test("renders progress bar when CMMB mode", () => {
        render(
            <CapacityCard
                viewMode={VIEW_MODES.CMMB}
                capacityData={capacityData}
                memCapacityData={memData}
                isLoading={false}
            />
        );

        expect(screen.getByText(/Used Memory/i)).toBeInTheDocument();
        expect(screen.getByText(/Total:/i)).toBeInTheDocument();
    });
});

// ----------- BandwidthCard -----------
describe("BandwidthCard", () => {
    const bw = {
        max_bandwidth: 200,
        used_percentage_bandwidth: 50,
        used_bandwidth: 100,
    };


    test("renders bandwidth values", () => {
        render(<BandwidthCard isLoading={false} viewMode={VIEW_MODES.HOST} bandwidthData={bw} />);
        expect(screen.getByText("0 GBps")).toBeInTheDocument();
        expect(screen.getByText("200 GBps")).toBeInTheDocument();
      
    });
});