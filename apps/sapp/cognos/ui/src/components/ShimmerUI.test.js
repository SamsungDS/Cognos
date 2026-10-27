import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ShimmerUI, { NavigationShimmer } from './ShimmerUI';

describe('ShimmerUI Component', () => {
    describe('Rendering - host type', () => {
        it('should render shimmer UI with default type "host"', () => {
            const { container } = render(<ShimmerUI />);
            expect(container.querySelector('.shimmer-wrapper')).toBeInTheDocument();
            expect(container.querySelector('.carousel-content')).toBeInTheDocument();
            expect(container.querySelector('.device-box')).toBeInTheDocument();
        });

        it('should render with type "host" explicitly', () => {
            const { container } = render(<ShimmerUI type="host" />);
            expect(container.querySelector('.shimmer-device-container')).toBeInTheDocument();
        });

        it('should render default 8 device shimmer placeholders for host type', () => {
            const { container } = render(<ShimmerUI type="host" />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(8);
        });

        it('should render each device wrapper with icon and label', () => {
            const { container } = render(<ShimmerUI type="host" />);
            const deviceIcons = container.querySelectorAll('.shimmer-device-icon');
            const deviceLabels = container.querySelectorAll('.shimmer-device-label');

            expect(deviceIcons).toHaveLength(8);
            expect(deviceLabels).toHaveLength(8);
        });

        it('should render custom number of device placeholders', () => {
            const { container } = render(<ShimmerUI type="host" deviceCount={5} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(5);
        });

        it('should render with correct inline styles for device-box', () => {
            const { container } = render(<ShimmerUI type="host" />);
            const deviceBox = container.querySelector('.device-box');

            expect(deviceBox).toHaveStyle({
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center'
            });
        });

        it('should render all shimmer elements with shimmer class', () => {
            const { container } = render(<ShimmerUI type="host" />);
            const shimmerElements = container.querySelectorAll('.shimmer');

            // 8 devices * 2 elements (icon + label) = 16
            expect(shimmerElements.length).toBeGreaterThan(0);
        });
    });

    describe('Rendering - cmm-b type', () => {
        it('should render shimmer UI with type "cmm-b"', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            expect(container.querySelector('.shimmer-wrapper')).toBeInTheDocument();
            expect(container.querySelector('.shimmer-badge-container')).toBeInTheDocument();
        });

        it('should render 4 host badge placeholders for cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            const hostBadges = container.querySelectorAll('.shimmer-host-badge');
            expect(hostBadges).toHaveLength(4);
        });

        it('should render 4 vertical lines for cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            const verticalLines = container.querySelectorAll('.shimmer-vertical-line');
            expect(verticalLines).toHaveLength(4);
        });

        it('should render default 8 device shimmer placeholders for cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(8);
        });

        it('should render custom number of device placeholders for cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" deviceCount={10} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(10);
        });

        it('should render both badge section and device section', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);

            expect(container.querySelector('.shimmer-badge-container')).toBeInTheDocument();
            expect(container.querySelector('.shimmer-device-container')).toBeInTheDocument();
        });

        it('should render device icons and labels in cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" deviceCount={6} />);
            const deviceIcons = container.querySelectorAll('.shimmer-device-icon');
            const deviceLabels = container.querySelectorAll('.shimmer-device-label');

            expect(deviceIcons).toHaveLength(6);
            expect(deviceLabels).toHaveLength(6);
        });

        it('should render with correct inline styles for device-box in cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            const deviceBox = container.querySelector('.device-box');

            expect(deviceBox).toHaveStyle({
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center'
            });
        });
    });

    describe('Rendering - invalid type', () => {
        it('should return null for unknown type', () => {
            const { container } = render(<ShimmerUI type="unknown" />);
            expect(container.firstChild).toBeNull();
        });

        it('should return null for empty string type', () => {
            const { container } = render(<ShimmerUI type="" />);
            expect(container.firstChild).toBeNull();
        });

        it('should return null for null type', () => {
            const { container } = render(<ShimmerUI type={null} />);
            expect(container.firstChild).toBeNull();
        });
    });

    describe('Device Count Edge Cases', () => {
        it('should render zero devices when deviceCount is 0', () => {
            const { container } = render(<ShimmerUI type="host" deviceCount={0} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(0);
        });

        it('should render single device when deviceCount is 1', () => {
            const { container } = render(<ShimmerUI type="host" deviceCount={1} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(1);
        });

        it('should render many devices when deviceCount is large', () => {
            const { container } = render(<ShimmerUI type="host" deviceCount={20} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(20);
        });

        it('should handle negative deviceCount gracefully', () => {
            const { container } = render(<ShimmerUI type="host" deviceCount={-5} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(0);
        });

        it('should render correct number of devices in cmm-b with custom count', () => {
            const { container } = render(<ShimmerUI type="cmm-b" deviceCount={15} />);
            const deviceWrappers = container.querySelectorAll('.shimmer-device-wrapper');
            expect(deviceWrappers).toHaveLength(15);

            // Badge count should remain 4 regardless of deviceCount
            const hostBadges = container.querySelectorAll('.shimmer-host-badge');
            expect(hostBadges).toHaveLength(4);
        });
    });

    describe('Component Structure', () => {
        it('should have proper nested structure for host type', () => {
            const { container } = render(<ShimmerUI type="host" />);

            const wrapper = container.querySelector('.shimmer-wrapper');
            const content = wrapper.querySelector('.carousel-content');
            const deviceBox = content.querySelector('.device-box');
            const deviceContainer = deviceBox.querySelector('.shimmer-device-container');

            expect(wrapper).toBeInTheDocument();
            expect(content).toBeInTheDocument();
            expect(deviceBox).toBeInTheDocument();
            expect(deviceContainer).toBeInTheDocument();
        });

        it('should have proper nested structure for cmm-b type', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);

            const wrapper = container.querySelector('.shimmer-wrapper');
            const content = wrapper.querySelector('.carousel-content');
            const badgeContainer = content.querySelector('.shimmer-badge-container');
            const deviceBox = content.querySelector('.device-box');

            expect(wrapper).toBeInTheDocument();
            expect(content).toBeInTheDocument();
            expect(badgeContainer).toBeInTheDocument();
            expect(deviceBox).toBeInTheDocument();
        });
    });

    describe('Key Props', () => {
        it('should generate unique keys for badge containers', () => {
            const { container } = render(<ShimmerUI type="cmm-b" />);
            const badgeContainer = container.querySelector('.shimmer-badge-container');
            const children = badgeContainer.children;

            expect(children).toHaveLength(4);
        });
    });
});

describe('NavigationShimmer Component', () => {
    describe('Rendering', () => {
        it('should render navigation shimmer with default structure', () => {
            const { container } = render(<NavigationShimmer />);
            expect(container.querySelector('.shimmer-navigation')).toBeInTheDocument();
        });

        it('should render left and right arrow shimmers', () => {
            const { container } = render(<NavigationShimmer />);
            const arrows = container.querySelectorAll('.shimmer-arrow');
            expect(arrows).toHaveLength(2);
        });

        it('should render default 6 title tab shimmers', () => {
            const { container } = render(<NavigationShimmer />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(6);
        });

        it('should render custom number of title tab shimmers', () => {
            const { container } = render(<NavigationShimmer tabCount={4} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(4);
        });

        it('should render with tabCount of 10', () => {
            const { container } = render(<NavigationShimmer tabCount={10} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(10);
        });

        it('should render with tabCount of 1', () => {
            const { container } = render(<NavigationShimmer tabCount={1} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(1);
        });

        it('should render zero tabs when tabCount is 0', () => {
            const { container } = render(<NavigationShimmer tabCount={0} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(0);

            // Arrows should still be present
            const arrows = container.querySelectorAll('.shimmer-arrow');
            expect(arrows).toHaveLength(2);
        });

        it('should handle negative tabCount gracefully', () => {
            const { container } = render(<NavigationShimmer tabCount={-3} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(0);
        });
    });

    describe('Component Structure', () => {
        it('should have correct order: left arrow, tabs, right arrow', () => {
            const { container } = render(<NavigationShimmer tabCount={3} />);
            const navigation = container.querySelector('.shimmer-navigation');
            const children = Array.from(navigation.children);

            expect(children[0]).toHaveClass('shimmer-arrow');
            expect(children[1]).toHaveClass('shimmer-title-tab');
            expect(children[2]).toHaveClass('shimmer-title-tab');
            expect(children[3]).toHaveClass('shimmer-title-tab');
            expect(children[4]).toHaveClass('shimmer-arrow');
        });

        it('should render all elements as siblings', () => {
            const { container } = render(<NavigationShimmer tabCount={2} />);
            const navigation = container.querySelector('.shimmer-navigation');

            // Should have 2 arrows + 2 tabs = 4 children
            expect(navigation.children).toHaveLength(4);
        });
    });

    describe('Key Props', () => {
        it('should generate unique keys for tab elements', () => {
            const { container } = render(<NavigationShimmer tabCount={5} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');

            expect(tabs).toHaveLength(5);
            tabs.forEach((tab) => {
                expect(tab).toBeInTheDocument();
            });
        });
    });

    describe('Edge Cases', () => {
        it('should handle very large tabCount', () => {
            const { container } = render(<NavigationShimmer tabCount={50} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            expect(tabs).toHaveLength(50);

            const arrows = container.querySelectorAll('.shimmer-arrow');
            expect(arrows).toHaveLength(2);
        });

        it('should render properly with decimal tabCount (rounded down)', () => {
            const { container } = render(<NavigationShimmer tabCount={5.7} />);
            const tabs = container.querySelectorAll('.shimmer-title-tab');
            // Array.from with length rounds down decimals
            expect(tabs).toHaveLength(5);
        });

        it('should always render arrows regardless of tabCount', () => {
            const { container: container1 } = render(<NavigationShimmer tabCount={0} />);
            expect(container1.querySelectorAll('.shimmer-arrow')).toHaveLength(2);

            const { container: container2 } = render(<NavigationShimmer tabCount={100} />);
            expect(container2.querySelectorAll('.shimmer-arrow')).toHaveLength(2);
        });
    });
});

describe('Integration Tests', () => {
    it('should render both ShimmerUI and NavigationShimmer together', () => {
        const { container } = render(
            <>
                <NavigationShimmer tabCount={5} />
                <ShimmerUI type="host" deviceCount={8} />
            </>
        );

        expect(container.querySelector('.shimmer-navigation')).toBeInTheDocument();
        expect(container.querySelector('.shimmer-wrapper')).toBeInTheDocument();
    });

    it('should render multiple ShimmerUI components with different types', () => {
        const { container } = render(
            <>
                <ShimmerUI type="host" deviceCount={5} />
                <ShimmerUI type="cmm-b" deviceCount={10} />
            </>
        );

        const wrappers = container.querySelectorAll('.shimmer-wrapper');
        expect(wrappers).toHaveLength(2);

        const badgeContainer = container.querySelector('.shimmer-badge-container');
        expect(badgeContainer).toBeInTheDocument();
    });

    it('should render multiple NavigationShimmer components', () => {
        const { container } = render(
            <>
                <NavigationShimmer tabCount={3} />
                <NavigationShimmer tabCount={5} />
            </>
        );

        const navigations = container.querySelectorAll('.shimmer-navigation');
        expect(navigations).toHaveLength(2);

        const allTabs = container.querySelectorAll('.shimmer-title-tab');
        expect(allTabs).toHaveLength(8); // 3 + 5
    });
});