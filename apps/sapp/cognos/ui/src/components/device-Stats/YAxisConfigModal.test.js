import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import YAxisConfigModal from './YAxisConfigModal';

describe('YAxisConfigModal', () => {
    const mockOnClose = jest.fn();
    const mockOnSave = jest.fn();

    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('Rendering', () => {
        it('should not render when isOpen is false', () => {
            const { container } = render(
                <YAxisConfigModal
                    isOpen={false}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );
            expect(container.firstChild).toBeNull();
        });

        it('should render when isOpen is true', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );
            expect(screen.getByText('Configure Y-Axis Range')).toBeInTheDocument();
        });

        it('should render all form elements', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            expect(screen.getByLabelText('Minimum value')).toBeInTheDocument();
            expect(screen.getByLabelText('Maximum value')).toBeInTheDocument();
            expect(screen.getByText('Reset to Default')).toBeInTheDocument();
            expect(screen.getByText('Cancel')).toBeInTheDocument();
            expect(screen.getByText('Apply')).toBeInTheDocument();
        });

        it('should display current min and max values', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={10}
                    currentMax={200}
                />
            );

            expect(screen.getByLabelText('Minimum value')).toHaveValue(10);
            expect(screen.getByLabelText('Maximum value')).toHaveValue(200);
        });

        it('should display default values when currentMin and currentMax are not provided', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                />
            );

            expect(screen.getByLabelText('Minimum value')).toHaveValue(0);
            expect(screen.getByLabelText('Maximum value')).toHaveValue(100);
        });
    });

    describe('User Interactions', () => {
        it('should update minimum value on input change', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            fireEvent.change(minInput, { target: { value: '25' } });
            expect(minInput).toHaveValue(25);
        });

        it('should update maximum value on input change', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const maxInput = screen.getByLabelText('Maximum value');
            fireEvent.change(maxInput, { target: { value: '150' } });
            expect(maxInput).toHaveValue(150);
        });
    });

    describe('Validation', () => {
        it('should show error when min value is not a number', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: 'abc' } });
            fireEvent.click(applyButton);

            expect(screen.getByRole('alert')).toHaveTextContent('Please enter valid numbers');
            expect(mockOnSave).not.toHaveBeenCalled();
            expect(mockOnClose).not.toHaveBeenCalled();
        });

        it('should show error when max value is not a number', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(maxInput, { target: { value: 'xyz' } });
            fireEvent.click(applyButton);

            expect(screen.getByRole('alert')).toHaveTextContent('Please enter valid numbers');
            expect(mockOnSave).not.toHaveBeenCalled();
            expect(mockOnClose).not.toHaveBeenCalled();
        });

        it('should show error when min value is greater than or equal to max value', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '100' } });
            fireEvent.change(maxInput, { target: { value: '50' } });
            fireEvent.click(applyButton);

            expect(screen.getByRole('alert')).toHaveTextContent(
                'Minimum value must be less than maximum value'
            );
            expect(mockOnSave).not.toHaveBeenCalled();
            expect(mockOnClose).not.toHaveBeenCalled();
        });

        it('should show error when min value equals max value', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '50' } });
            fireEvent.change(maxInput, { target: { value: '50' } });
            fireEvent.click(applyButton);

            expect(screen.getByRole('alert')).toHaveTextContent(
                'Minimum value must be less than maximum value'
            );
        });

        it('should show error when min value is negative', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '-10' } });
            fireEvent.click(applyButton);

            expect(screen.getByRole('alert')).toHaveTextContent('Values cannot be negative');
            expect(mockOnSave).not.toHaveBeenCalled();
        });
    });

    describe('Button Actions', () => {
        it('should call onSave and onClose with correct values when Apply is clicked with valid data', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '10' } });
            fireEvent.change(maxInput, { target: { value: '90' } });
            fireEvent.click(applyButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: 10, max: 90 });
            expect(mockOnClose).toHaveBeenCalled();
        });

        it('should clear error and call onClose when Cancel is clicked', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const applyButton = screen.getByText('Apply');
            const cancelButton = screen.getByText('Cancel');

            fireEvent.change(minInput, { target: { value: 'invalid' } });
            fireEvent.click(applyButton);
            expect(screen.getByRole('alert')).toBeInTheDocument();

            fireEvent.click(cancelButton);
            expect(mockOnClose).toHaveBeenCalled();
        });

        it('should reset values to default and call onSave and onClose when Reset is clicked', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={20}
                    currentMax={80}
                />
            );

            const resetButton = screen.getByText('Reset to Default');
            fireEvent.click(resetButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: null, max: null });
            expect(mockOnClose).toHaveBeenCalled();
        });

        it('should clear error when Reset is clicked', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const applyButton = screen.getByText('Apply');
            const resetButton = screen.getByText('Reset to Default');

            fireEvent.change(minInput, { target: { value: 'invalid' } });
            fireEvent.click(applyButton);
            expect(screen.getByRole('alert')).toBeInTheDocument();

            fireEvent.click(resetButton);
            expect(mockOnSave).toHaveBeenCalledWith({ min: null, max: null });
            expect(mockOnClose).toHaveBeenCalled();
        });
    });

    describe('Error Handling', () => {
        it('should clear error message after successful submission', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: 'invalid' } });
            fireEvent.click(applyButton);
            expect(screen.getByRole('alert')).toBeInTheDocument();

            fireEvent.change(minInput, { target: { value: '10' } });
            fireEvent.change(maxInput, { target: { value: '90' } });
            fireEvent.click(applyButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: 10, max: 90 });
        });

        it('should not display error message initially', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        });
    });

    describe('Edge Cases', () => {
        it('should handle decimal values correctly', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '10.5' } });
            fireEvent.change(maxInput, { target: { value: '90.75' } });
            fireEvent.click(applyButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: 10.5, max: 90.75 });
        });

        it('should handle very large numbers', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={0}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '1000000' } });
            fireEvent.change(maxInput, { target: { value: '9999999' } });
            fireEvent.click(applyButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: 1000000, max: 9999999 });
        });

        it('should handle zero as a valid minimum value', () => {
            render(
                <YAxisConfigModal
                    isOpen={true}
                    onClose={mockOnClose}
                    onSave={mockOnSave}
                    currentMin={10}
                    currentMax={100}
                />
            );

            const minInput = screen.getByLabelText('Minimum value');
            const maxInput = screen.getByLabelText('Maximum value');
            const applyButton = screen.getByText('Apply');

            fireEvent.change(minInput, { target: { value: '0' } });
            fireEvent.change(maxInput, { target: { value: '50' } });
            fireEvent.click(applyButton);

            expect(mockOnSave).toHaveBeenCalledWith({ min: 0, max: 50 });
            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        });
    });
});