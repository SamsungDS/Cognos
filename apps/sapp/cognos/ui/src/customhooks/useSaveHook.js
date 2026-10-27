const useSaveHook = (setMemboxData, setShow, apiEndpoint) => {


  const handleSave = async (formData) => {
    setShow(false);

    try {
      const response = await fetch(`${apiEndpoint}/create_lmd`, {
        mode: 'cors',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(formData)
      });

      if (response.ok) {
        console.log("Successfully created LMD: ", formData);
        const data = await response.json();
        setMemboxData(data);
      }
    } catch (error) {
      console.error('Error handling save:', error);
    }
  };

  return { handleSave };
};

export default useSaveHook;