from mpi4py import MPI
import sys,os
software = "/data/shared/Software/"
if(not software in sys.path):
    sys.path.append(software)


# print("Mooop")
if(len(sys.argv) != 3):
    raise ValueError("MPIKerasTrail_execute.py -- Incorrect number of arguments.")

archive_dir = sys.argv[1]
hashcode = sys.argv[2]
# numProcesses = sys.argv[3]

print(archive_dir, hashcode)


from CMS_SURF_2016.utils.archiving import KerasTrial
from CMS_SURF_2016.utils.MPIArchiving import MPI_KerasTrial

trial = MPI_KerasTrial.find_by_hashcode(archive_dir, hashcode)
if(trial == None):
    raise ValueError("hashcode does not exist")
if(not isinstance(trial, MPI_KerasTrial)):
    raise TypeError("Trial is not MPI_KerasTrial, got type %r" % type(trial))
trial._execute_MPI(numProcesses)
print(sys.argv[0])
print(sys.argv[1])
