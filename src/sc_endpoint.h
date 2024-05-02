#ifndef __CXL_PLUGIN_FM_ENDPOINT_H__
#define __CXL_PLUGIN_FM_ENDPOINT_H__


#include <string>

/**
* @brief simple class endpoint
* @details This class encapsulates string variable
*          and provides modifiers & accessors for it.
*/
class endpoint
{
    private:
        std::string ep; /**< strinv variable ep*/
    
    public:

	/**
	 * @brief default constructor
	*/ 
	endpoint()=default;

	/**
        * @brief endpoint constructor with one parameter.
        * @details This constructor takes string parameter.
        * @param ep string value of cxl device endpoint.
        */
	endpoint(std::string ep){
	    this->ep=ep;
	}

        ~endpoint(){}

	/**
        * @brief mutator of endpoint variable.
        * @details set endpoint value to data member.
        * @param ep string value of cxl device endpoint.
        */
        void set_endpoint(std::string ep){
	    this->ep=ep;    
	}

        /**
        * @brief accessor of endpoint variable.
        * @details get endpoint value.
        */
	std::string get_endpoint(){
	    return ep;
	}
	
};


#endif
