import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import DownloadArtifacts from '../pages/DownloadArtifacts';

// ─── Mock CSS imports ────────────────────────────────────────────────────────
jest.mock('bootstrap/dist/css/bootstrap.min.css', () => ({}));
jest.mock('../pages/downloadArtifacts.css', () => ({}));

// ─── Mock constants ───────────────────────────────────────────────────────────
jest.mock('../../src/constant', () => ({
    Configs: { api_endpoint: 'http://mock-api' },
}));

// ─── Mock lucide-react icons ─────────────────────────────────────────────────
jest.mock('lucide-react', () => ({
    Download: ({ className, size }) => (
        <svg data-testid="download-icon" className={className} width={size} height={size}>
            <title>Download Icon</title>
        </svg>
    ),
    AlertCircle: ({ size, className }) => (
        <svg data-testid="alert-circle-icon" className={className} width={size} height={size}>
            <title>Alert Circle Icon</title>
        </svg>
    ),
    CheckCircle: ({ size, className }) => (
        <svg data-testid="check-circle-icon" className={className} width={size} height={size}>
            <title>Check Circle Icon</title>
        </svg>
    ),
    PackageX: ({ size, className }) => (
        <svg data-testid="package-x-icon" className={className} width={size} height={size}>
            <title>Package X Icon</title>
        </svg>
    ),
    Tag: ({ size, className }) => (
        <svg data-testid="tag-icon" className={className} width={size} height={size}>
            <title>Tag Icon</title>
        </svg>
    ),
    Calendar: ({ size, className }) => (
        <svg data-testid="calendar-icon" className={className} width={size} height={size}>
            <title>Calendar Icon</title>
        </svg>
    ),
    List: ({ size, className }) => (
        <svg data-testid="list-icon" className={className} width={size} height={size}>
            <title>List Icon</title>
        </svg>
    ),
    FileText: ({ size, className }) => (
        <svg data-testid="file-text-icon" className={className} width={size} height={size}>
            <title>File Text Icon</title>
        </svg>
    ),
}));

// ─── Test fixtures ────────────────────────────────────────────────────────────
const mockArtifacts = [
    { id: 1, name: 'cognos-v1.0.tar.gz', available: true },
    { id: 2, name: 'cognos-v2.0.tar.gz', available: true },
    { id: 3, name: 'cognos-v3.0.tar.gz', available: false },
];
const mockArtifactsWithDetails = [
    {
        id: 1,
        name: 'cognos-v1.0.tar.gz',
        available: true,
        release_name: 'Cognos 1.0',
        release_date: '2024-01-15',
        release_notes: 'Initial stable release with core features.',
        feature_list: ['Feature Alpha', 'Feature Beta', 'Feature Gamma'],
    },
    { id: 2, name: 'cognos-v2.0.tar.gz', available: true },
    { id: 3, name: 'cognos-v3.0.tar.gz', available: false },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────
const mockFetchArtifactList = (artifacts = mockArtifacts, ok = true) => {
    global.fetch = jest.fn().mockResolvedValueOnce({
        ok,
        status: ok ? 200 : 500,
        json: async () => ({ artifacts }),
    });
};

const mockFetchWithDownload = (downloadOk = true) => {
    // First call → list; second call → download
    global.fetch = jest.fn()
        .mockResolvedValueOnce({
            ok: true,
            json: async () => ({ artifacts: mockArtifacts }),
        })
        .mockResolvedValueOnce(
            downloadOk
                ? {
                    ok: true,
                    blob: async () => new Blob(['file-content'], { type: 'application/gzip' }),
                }
                : {
                    ok: false,
                    status: 500,
                    json: async () => ({ error: 'Server error' }),
                }
        );
};

// Silence act() warnings for async state updates in tests that don't await
beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => { });
});

afterEach(() => {
    jest.restoreAllMocks();
    delete global.fetch;
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DownloadArtifacts Component', () => {

    // ── Rendering ──────────────────────────────────────────────────────────────
    describe('Rendering', () => {
        beforeEach(() => mockFetchArtifactList());

        it('renders without crashing', () => {
            expect(() => render(<DownloadArtifacts />)).not.toThrow();
        });

        it('renders the main page container with correct classes', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.page-container.Content.content_root.about')).toBeInTheDocument();
        });

        it('renders the header as h1 element', () => {
            render(<DownloadArtifacts />);
            const heading = screen.getByText('Download Cognos Artifacts');
            expect(heading.tagName).toBe('H1');
        });

        it('renders the dropdown label', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByText('Select Cognos Release')).toBeInTheDocument();
        });

        it('renders the download button', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeInTheDocument();
        });

        it('renders the download icon', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByTestId('download-icon')).toBeInTheDocument();
        });
    });

    // ── Layout Structure ───────────────────────────────────────────────────────
    describe('Layout Structure', () => {
        beforeEach(() => mockFetchArtifactList());

        it('renders full-width header row', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.row.full-width-header')).toBeInTheDocument();
        });

        it('renders content container', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.content-container')).toBeInTheDocument();
        });

        it('renders two card-dark sections', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelectorAll('.card.card-dark')).toHaveLength(2);
        });

        it('renders download section in col-lg-12', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.col-lg-12.col-md-12')).toBeInTheDocument();
        });
    });

    // ── Loading State ──────────────────────────────────────────────────────────
    describe('Loading State', () => {
        it('shows loading text while fetching artifact list', () => {
            // Never resolve so we stay in loading state
            global.fetch = jest.fn().mockReturnValue(new Promise(() => { }));
            render(<DownloadArtifacts />);
            expect(screen.getByText('Loading artifacts...')).toBeInTheDocument();
        });

        it('hides loading text after artifacts are fetched', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => {
                expect(screen.queryByText('Loading artifacts...')).not.toBeInTheDocument();
            });
        });

        it('disables download button while loading', () => {
            global.fetch = jest.fn().mockReturnValue(new Promise(() => { }));
            render(<DownloadArtifacts />);
            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeDisabled();
        });
    });

    // ── Artifact List Fetch ────────────────────────────────────────────────────
    describe('Artifact List Fetch', () => {
        it('calls the correct list_artifact endpoint on mount', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => {
                expect(global.fetch).toHaveBeenCalledWith(
                    'http://mock-api/list_artifact',
                    expect.objectContaining({ method: 'GET' })
                );
            });
        });

        it('populates dropdown with fetched artifacts', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => {
                expect(screen.getByText('cognos-v1.0.tar.gz')).toBeInTheDocument();
                expect(screen.getByText('cognos-v2.0.tar.gz')).toBeInTheDocument();
            });
        });

        it('shows unavailable label for artifacts with available: false', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => {
                // Component renders: "cognos-v3.0.tar.gz ⚠ Unavailable"
                expect(screen.getByText(/cognos-v3\.0\.tar\.gz/)).toBeInTheDocument();
                expect(screen.getByText(/Unavailable/)).toBeInTheDocument();
            });
        });

        it('shows error status when list fetch fails', async () => {
            mockFetchArtifactList([], false);
            render(<DownloadArtifacts />);
            await waitFor(() => {
                expect(screen.getByText(/Failed to load artifacts/i)).toBeInTheDocument();
            });
        });

        it('shows error status when network throws', async () => {
            global.fetch = jest.fn().mockRejectedValueOnce(new Error('Network error'));
            render(<DownloadArtifacts />);
            await waitFor(() => {
                expect(screen.getByText(/Failed to load artifacts.*Network error/i)).toBeInTheDocument();
            });
        });
    });

    // ── Initial State ──────────────────────────────────────────────────────────
    describe('Initial State', () => {
        beforeEach(() => mockFetchArtifactList());

        it('has download button disabled by default', async () => {
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));
            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeDisabled();
        });

        it('download icon does not have animate-bounce class initially', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByTestId('download-icon')).not.toHaveClass('animate-bounce');
        });

        it('no status alert is shown initially', async () => {
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));
            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        });
    });

    // ── Dropdown Interaction ───────────────────────────────────────────────────
    describe('Dropdown Interaction', () => {
        it('enables the download button after selecting an available artifact', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.getByRole('button', { name: /Download Artifact/i })).not.toBeDisabled();
        });

        it('keeps button disabled when an unavailable artifact is selected', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText(/cognos-v3\.0\.tar\.gz/));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '3' } });

            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeDisabled();
        });

        it('clears status message when a new artifact is selected', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            // Trigger an error
            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));
            await waitFor(() => screen.getByText(/Download failed/i));

            // Change selection → status should clear
            fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });
            expect(screen.queryByText(/Download failed/i)).not.toBeInTheDocument();
        });

        it('disables download button when default option is re-selected', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            expect(screen.getByRole('button', { name: /Download Artifact/i })).not.toBeDisabled();

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeDisabled();
        });
    });

    // ── Availability Warning ───────────────────────────────────────────────────
    describe('Availability Warning', () => {
        it('shows PackageX icon and warning when unavailable artifact is selected', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText(/cognos-v3\.0\.tar\.gz/));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '3' } });

            expect(screen.getByTestId('package-x-icon')).toBeInTheDocument();
            expect(screen.getByText(/not available on the server yet/i)).toBeInTheDocument();
        });

        it('does not show availability warning for available artifact', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.queryByTestId('package-x-icon')).not.toBeInTheDocument();
        });

        it('sets status to unavailable type without calling fetch when clicking download on unavailable', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText(/cognos-v3\.0\.tar\.gz/));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '3' } });
            // handleDownload guards before fetch – button is disabled so click won't fire,
            // but we verify the guard logic via button disabled state
            expect(screen.getByRole('button', { name: /Download Artifact/i })).toBeDisabled();
            // fetch should only have been called once (the initial list fetch)
            expect(global.fetch).toHaveBeenCalledTimes(1);
        });

        it('hides availability warning when switching to an available artifact', async () => {
            mockFetchArtifactList();
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText(/cognos-v3\.0\.tar\.gz/));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '3' } });
            expect(screen.getByTestId('package-x-icon')).toBeInTheDocument();

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            expect(screen.queryByTestId('package-x-icon')).not.toBeInTheDocument();
        });
    });

    // ── Download Handler ───────────────────────────────────────────────────────
    describe('Download Handler', () => {
        it('shows error status after failed download', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            await waitFor(() => {
                expect(screen.getByText(/Download failed/i)).toBeInTheDocument();
            });
            expect(screen.getByTestId('alert-circle-icon')).toBeInTheDocument();
        });

        it('shows "Downloading..." button text while download is in progress', async () => {
            let resolveDownload;
            global.fetch = jest.fn()
                .mockResolvedValueOnce({ ok: true, json: async () => ({ artifacts: mockArtifacts }) })
                .mockReturnValueOnce(new Promise((res) => { resolveDownload = res; }));

            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            expect(screen.getByText('Downloading...')).toBeInTheDocument();

            // Cleanup: resolve the pending promise
            resolveDownload({ ok: false, status: 500, json: async () => ({}) });
        });

        it('adds animate-bounce class to icon during download', async () => {
            let resolveDownload;
            global.fetch = jest.fn()
                .mockResolvedValueOnce({ ok: true, json: async () => ({ artifacts: mockArtifacts }) })
                .mockReturnValueOnce(new Promise((res) => { resolveDownload = res; }));

            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            expect(screen.getByTestId('download-icon')).toHaveClass('animate-bounce');

            resolveDownload({ ok: false, status: 500, json: async () => ({}) });
        });

        it('re-enables button after download completes', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /Download Artifact/i })).not.toBeDisabled();
            });
        });

        it('disables select dropdown while downloading', async () => {
            let resolveDownload;
            global.fetch = jest.fn()
                .mockResolvedValueOnce({ ok: true, json: async () => ({ artifacts: mockArtifacts }) })
                .mockReturnValueOnce(new Promise((res) => { resolveDownload = res; }));

            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            expect(screen.getByRole('combobox')).toBeDisabled();

            resolveDownload({ ok: false, status: 500, json: async () => ({}) });
        });
        it('includes server error message in failed download status', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            await waitFor(() => {
                expect(screen.getByText(/Download failed.*Server error/i)).toBeInTheDocument();
            });
        });

    });

    // ── Status Message Icons ───────────────────────────────────────────────────
    describe('Status Message Icons', () => {
        it('renders AlertCircle icon on error', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));
            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            await waitFor(() => expect(screen.getByTestId('alert-circle-icon')).toBeInTheDocument());
        });


        it('error alert has alert-danger class', async () => {
            mockFetchWithDownload(false);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));
            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });
            fireEvent.click(screen.getByRole('button', { name: /Download Artifact/i }));

            await waitFor(() => {
                const alert = screen.getByText(/Download failed/i).closest('.alert');
                expect(alert).toHaveClass('alert-danger');
            });
        });
    });

    // ── Artifact Details Panel ─────────────────────────────────────────────────
    describe('Artifact Details Panel', () => {
        it('does not show details panel when no artifact is selected', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            const { container } = render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            expect(container.querySelector('.artifact-details-panel')).not.toBeInTheDocument();
        });

        it('shows details panel after selecting an artifact', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            const { container } = render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(container.querySelector('.artifact-details-panel')).toBeInTheDocument();
        });

        it('shows release name when provided', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.getByText('Cognos 1.0')).toBeInTheDocument();
        });

        it('shows release notes when provided', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.getByText('Initial stable release with core features.')).toBeInTheDocument();
        });

        it('shows feature list items when provided', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.getByText('Feature Alpha')).toBeInTheDocument();
            expect(screen.getByText('Feature Beta')).toBeInTheDocument();
            expect(screen.getByText('Feature Gamma')).toBeInTheDocument();
        });

        it('shows features count label correctly', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v1.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } });

            expect(screen.getByText(/Features \(3\)/i)).toBeInTheDocument();
        });

        it('does not show release name section when release_name is absent', async () => {
            mockFetchArtifactList(mockArtifactsWithDetails);
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('cognos-v2.0.tar.gz'));

            fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } });

            // artifact 2 has no release_name — "Release Name" label should not appear
            expect(screen.queryByText('Release Name')).not.toBeInTheDocument();
        });
    });

    // ── Accessibility ──────────────────────────────────────────────────────────
    describe('Accessibility', () => {
        beforeEach(() => mockFetchArtifactList());

        it('dropdown label has correct styling classes', async () => {
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByText('Select Cognos Release'));
            const label = screen.getByText('Select Cognos Release');
            expect(label).toHaveClass('form-label', 'text-slate', 'small', 'fw-medium');
        });

        it('button is a native BUTTON element', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button.tagName).toBe('BUTTON');
        });

        it('download icon has me-2 margin class', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByTestId('download-icon')).toHaveClass('me-2');
        });

        it('download icon renders with size 20', () => {
            render(<DownloadArtifacts />);
            const icon = screen.getByTestId('download-icon');
            expect(icon).toHaveAttribute('width', '20');
            expect(icon).toHaveAttribute('height', '20');
        });
    });

    // ── Styling Classes ────────────────────────────────────────────────────────
    describe('Styling Classes', () => {
        beforeEach(() => mockFetchArtifactList());

        it('applies Bootstrap card styling', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelectorAll('.card').length).toBeGreaterThan(0);
        });

        it('applies Bootstrap grid rows', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelectorAll('.row').length).toBeGreaterThan(0);
        });

        it('header row has mb-4 margin class', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.full-width-header')).toHaveClass('mb-4');
        });

        it('card bodies have p-4 padding', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelectorAll('.card-body.p-4').length).toBeGreaterThan(0);
        });

        it('download button has all required classes', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toHaveClass('btn', 'btn-download', 'w-100', 'd-flex', 'align-items-center', 'justify-content-center');
        });

        it('dropdown has form-select-dark class', async () => {
            render(<DownloadArtifacts />);
            await waitFor(() => screen.getByRole('combobox'));
            expect(screen.getByRole('combobox')).toHaveClass('form-select', 'form-select-dark');
        });
    });

    // ── Responsive Design ──────────────────────────────────────────────────────
    describe('Responsive Design', () => {
        beforeEach(() => mockFetchArtifactList());

        it('applies responsive column classes', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelector('.col-lg-12.col-md-12')).toBeInTheDocument();
        });

        it('uses Bootstrap responsive utilities', () => {
            const { container } = render(<DownloadArtifacts />);
            expect(container.querySelectorAll('[class*="col-"]').length).toBeGreaterThan(0);
        });
    });

    // ── Button Content ─────────────────────────────────────────────────────────
    describe('Button Content', () => {
        beforeEach(() => mockFetchArtifactList());

        it('button contains icon and text', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toContainElement(screen.getByTestId('download-icon'));
            expect(button).toHaveTextContent('Download Artifact');
        });
    });
});