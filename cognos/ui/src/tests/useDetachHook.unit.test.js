import useDetachHook from '../customhooks/useDetachHook';

describe('useDetachHook', () => {
  const setMemboxDataMock = jest.fn();
  const setLmdDataMock = jest.fn();
  const handleDetachMemoryToggleMock = jest.fn();
  const selectedValueMock = { label: 'Host 1' };
  const apiEndpointMock = 'http://105.91.142.222:4000';

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should handle detachment successfully', async () => {
    const mockItem = { capacity: '128',
        capacity_units:  "GB",
        lmd: "D-2",
        mem_mode: "Direct",
        mem_type: "CMMD",
        pool: "",
        used_capacit : 0,
        used_capacity_units :  "GB" };
    const mockLmdData = [ {
        capacity: 128,
        capacity_units: 'GB',
        lmd: 'D-2',
        mem_mode: 'Direct',
        mem_type: 'CMMD',
        pool: '',
        used_capacity: 0,
        used_capacity_units: 'GB',
      } 
    ];
    const mockMemboxData = [ {
        capacity: 128,
        capacity_units: 'GB',
        lmd: 'D-2',
        mem_mode: 'Direct',
        mem_type: 'CMMD',
        used_capacity: 0,
        used_capacity_units: 'GB',
      } 
    ];

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.endsWith('/detach_lmd')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockLmdData),
        });
      } else if (url.endsWith('/lmds')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockMemboxData),
        });
      }
    });

    const { handleDetach } = useDetachHook(
      setMemboxDataMock,
      setLmdDataMock,
      handleDetachMemoryToggleMock,
      selectedValueMock,
      apiEndpointMock
    );

    await handleDetach(mockItem);

    expect(handleDetachMemoryToggleMock).toHaveBeenCalledTimes(1);
    expect(setLmdDataMock).toHaveBeenCalledWith(mockLmdData);
    expect(setMemboxDataMock).toHaveBeenCalledWith(mockMemboxData);
  });

  it('should handle detachment failure', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
    });

    const { handleDetach } = useDetachHook(
      setMemboxDataMock,
      setLmdDataMock,
      handleDetachMemoryToggleMock,
      selectedValueMock,
      apiEndpointMock
    );

 
    await handleDetach({ capacity: '128',
      capacity_units:  "GB",
      lmd: "D-2",
      mem_mode: "Direct",
      mem_type: "CMMD",
      used_capacity : 0,
      used_capacity_units :  "GB" 
    });

    expect(handleDetachMemoryToggleMock).toHaveBeenCalledTimes(1);
    expect(setLmdDataMock).not.toHaveBeenCalled();
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });
});