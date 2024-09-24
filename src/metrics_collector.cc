#include "metrics_collector.h"
#include <stdexcept>
#include <sys/wait.h>
#include <numa.h>
using namespace std;

/**
* @brief trigger metrics collection
* @details This method is a top level function;
	It triggers individual functions for
 	memory, cpu metrics collection, populate metric json
* @return 0 on success
*/
int MetricsCollector::get_system_metrics()
{
	try
	{
		metrics_command_cpu = "dstat --cpu 1 2";
		get_cpu_metrics(metrics_command_cpu);
		get_memory_metrics();
		populate_metric_event_fields();
		generate_json();
	}
	catch (const exception& e)
	{
		cerr << "Error in " + string(__FUNCTION__) + " : " + string(e.what()) << endl;
		return -1;
	}
	return 0;
}

/**
* @brief parse dstat output and get CPU usage
* @details This method parses dstat output
*          to get cpu usage
* @param line expected output line of dstat command
* @return CPU usage(double) parsed from dstat output
*/
double MetricsCollector::dstat_parser_cpu_usage(string line)
{
	if (line.empty())
	{
		throw std::invalid_argument("Error in " + string(__FUNCTION__) + " : " + string("dstat parser input empty"));
	}
	double cpu_usage = 0.0;
	try
	{
		string token;
		istringstream temp(line);
		char cpu_delim = ' ';
		vector <string> load_line;
		while (getline(temp, token, cpu_delim)) 
		{
			load_line.push_back(token);
		}
		string idle;
		unsigned int i = 0;
		unsigned int c = 0;
		for(;i<(unsigned int)load_line.size();i++)
		{
			if (load_line[i].empty())
			{
				continue;
			}
			else
			{
				c++;
			}
			if (c==3)
			{
				idle=load_line[i];
				break;
			}
		}
		double cpu_idle =  stod(idle);
		cpu_usage = 100.0 - cpu_idle;
	}
	catch (const exception& e)
	{
		throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
	}
	return cpu_usage;
}

/**
* @brief get host cpu metrics
* @details This method gets the output from dstat
*          and parses to get cpu usage
*/
void MetricsCollector::get_cpu_metrics(string cmd)
{
	try
	{
		char buffer[256];
		vector <string> output;
		FILE* pipe = popen(cmd.c_str(), "r");
		if (!pipe) 
		{
			cerr << "Error in " + string(__FUNCTION__) + " : error in popen for command: " + cmd << endl;
			throw runtime_error("Error in " + string(__FUNCTION__) + " : error in popen for command: " + cmd);
		}
		while (fgets(buffer, sizeof(buffer), pipe) != nullptr) 
		{
			output.push_back(buffer);
		}
		int status = pclose(pipe);
		if (status == -1)
		{
			cerr << "Error in " + string(__FUNCTION__) + " : error in pclose for command: " + cmd << endl;
			throw runtime_error("Error in " + string(__FUNCTION__) + " : error in pclose for command: " + cmd);
		}
		else if (status != 0)
		{
			cerr << "Error in " + string(__FUNCTION__) + " : error in execution for command: " + cmd + " exit status: " + to_string(WEXITSTATUS(status)) << endl;
			throw runtime_error("Error in " + string(__FUNCTION__) + " : error in execution for command: " + cmd + " exit status: " + to_string(WEXITSTATUS(status)));
		}
		else ;
		if (output.empty())
		{
			cerr << "Error in " + string(__FUNCTION__) + " : No output for command: " + cmd  << endl;
			throw runtime_error("Error in " + string(__FUNCTION__) + " : No output for command: " + cmd);
		}
		string line;
		double cpu_usage = 0.0;
		line.assign(output[output.size() -1]);
		cpu_usage = dstat_parser_cpu_usage(line);
		system_cpu_current_usage = cpu_usage;
	}
	catch (const exception& e)
	{
		throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
	}
}

/**
* @brief get memory metrics
* @details This method uses libnuma APIs to get numa node info
*          and calculates DRAM/CXL capacity, usage and free metrics
*/
void MetricsCollector::get_memory_metrics(void)
{
        try
       	{
		const unsigned long long MB = 1024*1024;
		int numa_node_count = numa_num_configured_nodes();
		cout << "No of configured numa nodes found = "<< numa_node_count <<endl;
		unsigned long long total_cxl_free = 0;
		unsigned long long total_cxl_size = 0;
		unsigned long long total_dram_free = 0;
		unsigned long long total_dram_size = 0;

		for(int i=0; i<numa_node_count; i++)
		{
			unsigned long long sz;
			struct bitmask* mask = numa_allocate_cpumask();
			if (mask == nullptr)
			{
				throw runtime_error("Error in bit mask allocation : numa_allocate_cpumask ");
			}
			long long size_raw = numa_node_size64(i,(long long*)&sz);
			if (size_raw == (long long )-1)
			{
				throw runtime_error("Error in getting numa node size : numa_node_size()");
			}
			unsigned long long size = size_raw / MB;
			unsigned long long free =  sz / MB;
			cout << "numanode =" << i << " size=" << size << " free=" << free << endl;
			int st = numa_node_to_cpus(i, mask);
			if (st != 0)
			{
				throw runtime_error("Error in numa_node_to_cpus, errno = " + to_string(errno) + ", error = " + strerror(errno));
			}
			unsigned long long val = *(mask->maskp);
			cout << "bitmask=" << mask->size << " val="  << val << endl;
			if (val == 0)
			{
				total_cxl_size += size;
				total_cxl_free += free;
			}
			else
			{
				total_dram_size += size;
				total_dram_free += free;
			}
			numa_free_cpumask(mask);
		}
		
		cout << "total dram size = " << total_dram_size << ", total dram free = " << total_dram_free << ", total dram usage = " << total_dram_size - total_dram_free << endl;
		cout << "total cxl size = " << total_cxl_size << ", total cxl free = " << total_cxl_free << ", total cxl usage = " << total_cxl_size - total_cxl_free << endl;
		
		cxl_memory_capacity = total_cxl_size;
		cxl_memory_current_usage = total_cxl_size - total_cxl_free;
		dram_memory_capacity = total_dram_size;
		dram_memory_current_usage = total_dram_size - total_dram_free;
		system_total_memory_capacity = total_cxl_size + total_dram_size;
		system_total_memory_current_usage = dram_memory_current_usage + cxl_memory_current_usage;
	}
	catch(const exception& e)
	{
		throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
	}
}

/**
* @brief populate metric event
* @details This method populates the metric event fields
*/
void MetricsCollector::populate_metric_event_fields(void)
{
	try
	{
		metric_event.type = "metric";
		char hostname[HOSTNAME_MAXLEN];
		gethostname(hostname, HOSTNAME_MAXLEN);
		string s(hostname);
		metric_event.source = s;
		metric_event.source_type = "application server";
		time_t now= std::time(0);
		tm* now_tm= std::gmtime(&now);
		char buf[size("yyyy-mm-ddThh:mm:ssZ")];
		strftime(buf, size("yyyy-mm-ddThh:mm:ssZ"), "%FT%TZ", now_tm);
		string s1(buf);
		metric_event.timestamp = s1;
		metric_event.category = "host system metrics";
		metric_event.description = "host cpu memory";
		metric_event.application = "cognos metric test";
		tuple <string,string> dram_cap;
		tuple <string,string> dram_usg;
		tuple <string,string> cxl_cap;
		tuple <string,string> cxl_usg;
		tuple <string,string> cpu_usg;
		dram_cap = make_tuple("dram_capacity_mb",to_string(dram_memory_capacity));
		dram_usg = make_tuple("dram_usage_mb",to_string(dram_memory_current_usage));
		cxl_cap = make_tuple("cxl_capacity_mb",to_string(cxl_memory_capacity));
		cxl_usg = make_tuple("cxl_usage_mb",to_string(cxl_memory_current_usage));
		cpu_usg = make_tuple("cpu_usage",to_string(system_cpu_current_usage));
		metric_event.observations.push_back(dram_cap);
		metric_event.observations.push_back(dram_usg);
		metric_event.observations.push_back(cxl_cap);
		metric_event.observations.push_back(cxl_usg);
		metric_event.observations.push_back(cpu_usg);
	}
	catch (const exception& e)
	{
		throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
	}
}

/**
* @brief generates the metric event json
* @details This method creates the json object from metric event object;
		   It creates the json string for zmq publish.
*/
void MetricsCollector::generate_json(void)
{
	try
	{
		json_t* metric_event_fields = json_object();
		json_t* jtemp = nullptr;
		jtemp = json_string(metric_event.type.c_str());
		json_object_set_new(metric_event_fields, "type", jtemp);
		jtemp = json_string(metric_event.source.c_str());
		json_object_set_new(metric_event_fields, "source", jtemp);
		jtemp = json_string(metric_event.source_type.c_str());
		json_object_set_new(metric_event_fields, "source_type", jtemp);
		jtemp = json_string(metric_event.timestamp.c_str());
		json_object_set_new(metric_event_fields, "timestamp", jtemp);
		jtemp = json_string(metric_event.description.c_str());
		json_object_set_new(metric_event_fields, "description", jtemp);
		jtemp = json_string(metric_event.category.c_str());
		json_object_set_new(metric_event_fields, "category", jtemp);
		jtemp = json_string(metric_event.application.c_str());
		json_object_set_new(metric_event_fields, "application", jtemp);
		json_t* metric_observations_fields = json_object();
		json_object_set_new(metric_event_fields, "observations", metric_observations_fields);
		for(auto item:metric_event.observations) // item is a tuple
		{
			if (get<0>(item).compare("cpu_usage") == 0)
			{
				jtemp = json_real(stod(get<1>(item)));
			}
			else
			{
				jtemp = json_integer(stoull(get<1>(item)));
			}
			json_object_set_new(metric_observations_fields, get<0>(item).c_str(), jtemp);
		}
		char event_metrics_json[METRIC_JSON_MAXLEN];
		char *buf = event_metrics_json;
		buf = json_dumps(metric_event_fields,METRIC_JSON_MAXLEN);
		string temp_json(buf);
		metric_event_json_string = temp_json;
	}
	catch(const exception& e)
	{
		throw runtime_error("Error in " + string(__FUNCTION__) + " : " + string(e.what()));
	}
}
