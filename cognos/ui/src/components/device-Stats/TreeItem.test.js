import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import TreeItem from './TreeItem';

// Mock CSS import
jest.mock('./deviceCard.css', () => ({}));

describe('TreeItem Component', () => {
    describe('Basic Rendering', () => {
        test('applies tree-style class', () => {
            const { container } = render(<TreeItem label="Test" />);
            const treeStyleDiv = container.querySelector('.tree-style');
            expect(treeStyleDiv).toBeInTheDocument();
        });

        test('renders without children by default', () => {
            const { container } = render(<TreeItem label="Test" />);
            expect(container.firstChild.children).toHaveLength(1); // Only the tree-style div
        });
    });

    describe('Level and Indentation', () => {
        test('applies default level 0 with no left margin', () => {
            const { container } = render(<TreeItem label="Root" />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '0px' });
        });

        test('applies correct margin for level 1', () => {
            const { container } = render(<TreeItem label="Level 1" level={1} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '15px' });
        });

        test('applies correct margin for level 2', () => {
            const { container } = render(<TreeItem label="Level 2" level={2} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '30px' });
        });

        test('applies correct margin for level 3', () => {
            const { container } = render(<TreeItem label="Level 3" level={3} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '45px' });
        });

        test('handles deep nesting levels', () => {
            const { container } = render(<TreeItem label="Deep" level={10} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '150px' });
        });
    });

    describe('Expand/Collapse Icons', () => {
        test('shows expand icon when hasChildren and not expanded', () => {
            render(<TreeItem label="Parent" hasChildren={true} isExpanded={false} />);
            expect(screen.getByText('▶')).toBeInTheDocument();
        });

        test('shows collapse icon when hasChildren and expanded', () => {
            render(<TreeItem label="Parent" hasChildren={true} isExpanded={true} />);
            expect(screen.getByText('▼')).toBeInTheDocument();
        });

        test('does not show icon when hasChildren is false', () => {
            render(<TreeItem label="Leaf" hasChildren={false} />);
            expect(screen.queryByText('▶')).not.toBeInTheDocument();
            expect(screen.queryByText('▼')).not.toBeInTheDocument();
        });

        test('icon has correct styling', () => {
            render(<TreeItem label="Parent" hasChildren={true} isExpanded={false} />);
            const icon = screen.getByText('▶');
            expect(icon).toHaveStyle({ marginRight: '5px', fontSize: '12px' });
        });
    });

    describe('Selection State', () => {
        test('applies transparent background when isSelected is false', () => {
            const { container } = render(<TreeItem label="Not Selected" isSelected={false} />);
            const treeStyleDiv = container.querySelector('.tree-style');
            expect(treeStyleDiv).toHaveStyle({ backgroundColor: 'transparent', color: '#ccc' });
        });

        test('applies default color when isSelected is not provided', () => {
            const { container } = render(<TreeItem label="Default" />);
            const treeStyleDiv = container.querySelector('.tree-style');
            expect(treeStyleDiv).toHaveStyle({ backgroundColor: 'transparent', color: '#ccc' });
        });
    });

    describe('Click Handlers', () => {
        test('stops propagation on click', () => {
            const mockToggle = jest.fn();
            const mockParentClick = jest.fn();

            const { container } = render(
                <div onClick={mockParentClick}>
                    <TreeItem
                        label="Child"
                        hasChildren={true}
                        toggleExpanded={mockToggle}
                        isExpanded={false}
                    />
                </div>
            );

            const treeItem = container.querySelector('.tree-style');
            fireEvent.click(treeItem);

            expect(mockToggle).toHaveBeenCalledTimes(1);
            expect(mockParentClick).not.toHaveBeenCalled();
        });

        test('does nothing when no handlers provided', () => {
            const { container } = render(<TreeItem label="No Handlers" />);
            const treeStyleDiv = container.querySelector('.tree-style');

            // Should not throw error
            expect(() => fireEvent.click(treeStyleDiv)).not.toThrow();
        });
    });

    describe('Hover Effects', () => {
        test('applies hover background when not selected on mouse enter', () => {
            const { container } = render(<TreeItem label="Hover Test" isSelected={false} />);
            const treeStyleDiv = container.querySelector('.tree-style');

            fireEvent.mouseEnter(treeStyleDiv);
            expect(treeStyleDiv).toHaveStyle({ backgroundColor: '#2a2a2a' });
        });

        test('removes hover background on mouse leave when not selected', () => {
            const { container } = render(<TreeItem label="Hover Test" isSelected={false} />);
            const treeStyleDiv = container.querySelector('.tree-style');

            fireEvent.mouseEnter(treeStyleDiv);
            fireEvent.mouseLeave(treeStyleDiv);
            expect(treeStyleDiv).toHaveStyle({ backgroundColor: 'transparent' });
        });

        test('does not apply hover background when selected', () => {
            const { container } = render(<TreeItem label="Selected Hover" isSelected={true} />);
            const treeStyleDiv = container.querySelector('.tree-style');

            const initialBgColor = treeStyleDiv.style.backgroundColor;
            fireEvent.mouseEnter(treeStyleDiv);
            expect(treeStyleDiv.style.backgroundColor).toBe(initialBgColor);
        });
        
    });

    describe('Children Rendering', () => {
        test('renders children when hasChildren is true and isExpanded is true', () => {
            render(
                <TreeItem label="Parent" hasChildren={true} isExpanded={true}>
                    <div data-testid="child-content">Child Content</div>
                </TreeItem>
            );

            expect(screen.getByTestId('child-content')).toBeInTheDocument();
        });

        test('does not render children when isExpanded is false', () => {
            render(
                <TreeItem label="Parent" hasChildren={true} isExpanded={false}>
                    <div data-testid="child-content">Child Content</div>
                </TreeItem>
            );

            expect(screen.queryByTestId('child-content')).not.toBeInTheDocument();
        });

        test('does not render children when hasChildren is false', () => {
            render(
                <TreeItem label="Leaf" hasChildren={false} isExpanded={true}>
                    <div data-testid="child-content">Child Content</div>
                </TreeItem>
            );

            expect(screen.queryByTestId('child-content')).not.toBeInTheDocument();
        });

        test('renders multiple children', () => {
            render(
                <TreeItem label="Parent" hasChildren={true} isExpanded={true}>
                    <div data-testid="child-1">Child 1</div>
                    <div data-testid="child-2">Child 2</div>
                    <div data-testid="child-3">Child 3</div>
                </TreeItem>
            );

            expect(screen.getByTestId('child-1')).toBeInTheDocument();
            expect(screen.getByTestId('child-2')).toBeInTheDocument();
            expect(screen.getByTestId('child-3')).toBeInTheDocument();
        });
    });

    describe('Edge Cases', () => {
        test('handles empty string label', () => {
            const { container } = render(<TreeItem label="" />);
            expect(container.firstChild).toBeInTheDocument();
        });

        test('handles negative level value', () => {
            const { container } = render(<TreeItem label="Negative" level={-1} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '-15px' });
        });

        test('handles zero level explicitly', () => {
            const { container } = render(<TreeItem label="Zero" level={0} />);
            const outerDiv = container.firstChild;
            expect(outerDiv).toHaveStyle({ marginLeft: '0px' });
        });
    });

    describe('Accessibility', () => {
        test('icon indicators are present for screen readers', () => {
            render(<TreeItem label="Parent" hasChildren={true} isExpanded={false} />);
            const icon = screen.getByText('▶');
            expect(icon).toBeInTheDocument();
        });
    });
});