''' 
archive.py
A system for archiving keras trials and input data
Author: Danny Weitekamp
e-mail: dannyweitekamp@gmail.com
''' 

import json
import hashlib
from keras.models import model_from_json
from keras.engine.training import Model
from CMS_SURF_2016.utils.callbacks import *
from keras.models import model_from_json
from keras.callbacks import *
import os
import copy
import h5py
import re
import types
import shutil
from CMS_SURF_2016.layers.lorentz import Lorentz, _lorentz
from CMS_SURF_2016.layers.slice import Slice

class Storable( object ):
    """An object that we can hash, archive as a json String, and reconstitute"""
    def __init__(self):
        '''Initialize the Storable'''
        self.hashcode = None
    def hash(self, rehash=False):
        '''Compute the hashcode for the Storable from its json string'''
        if(self.hashcode is None):
            self.hashcode = compute_hash(self.to_json())
        return self.hashcode
    def get_path(self):
        '''Gets the archive (blob) path from its hash'''
        json_str = self.to_json()
        hashcode = compute_hash(json_str)
        return get_blob_path(hashcode=hashcode, archive_dir=self.archive_dir) 
    def to_json( self ):
        '''Must implement a function that returns the json string corresponding to the Storable'''
        raise NotImplementedError( "Should have implemented to_json" )
    def write( self ):
        '''Must implement a function that write the Storable's json sring to its archive (blob) path'''
        raise NotImplementedError( "Should have implemented write" )
    def remove_from_archive(self):
        '''Removes all the data that the Storable has archived in its archive path'''
        folder = self.get_path()
        blob_dir, blob = split_hash(self.hash()) 
        parentfolder = self.archive_dir + "blobs/" +  blob_dir + '/'
        try:
            if(os.path.isdir(folder)):
                shutil.rmtree(folder)
            if(os.path.isdir(parentfolder) and os.listdir(parentfolder) == []):
                shutil.rmtree(parentfolder)
        except Exception as e:
            print(e)

    @staticmethod
    def find_by_hashcode( hashcode, archive_dir ):
        '''Must implement function that find a Storable by its hashcode'''
        raise NotImplementedError( "Should have implemented find_by_hashcode" )

class DataProcedure(Storable):
    '''A wrapper for archiving the results of data grabbing and preprocessing functions of the type X,Y getData where are X is the training
        data and Y contains the labels/targets for each entry'''
    def __init__(self, archive_dir,archive_getData, func,  *args, **kargs):
        Storable.__init__(self)
        if(isinstance(archive_dir, str) == False and isinstance(archive_dir, unicode) == False):
            raise TypeError("archive_dir must be str, but got %r" %type(archive_dir))
        if(isinstance(archive_getData, bool) == False):
            raise TypeError("archive_getData must be bool, but got %r" % type(archive_getData))
        if(isinstance(func, types.FunctionType) == False):
            raise TypeError("func must be function, but got %r" % type(func))

        self.archive_dir = archive_dir
        self.func = func.__name__
        self.func_module = func.__module__
        self.args = args
        self.kargs = kargs
        self.archive_getData = archive_getData

        def recurseStore(x):
            if(isinstance(x,Storable)):
                return x.to_json()
            else:
                return x.__dict__ 
                
        self.encoder = json.JSONEncoder(sort_keys=True, indent=4, default=recurseStore)
        self.X = None
        self.Y = None
    

    def set_encoder(self, encoder):
        '''Set the json encoder for the procedure in case its arguements are not json encodable'''
        self.encoder = encoder


    def to_json(self):
        '''Returns the json string for the Procedure with only its essential characteristics'''
        d = self.__dict__
        d = copy.deepcopy(d)

        d["class_name"] = self.__class__.__name__
        #Don't hash on verbose or verbosity if they are in the function
        if("verbose" in d.get("kargs", [])): del d['kargs']["verbose"]
        if("verbosity" in d.get("kargs", [])): del d['kargs']["verbosity"]

        del d["archive_dir"]
        if('encoder' in d): del d["encoder"]
        if('decoder' in d): del d["decoder"]
        del d["hashcode"]
        del d["X"]
        del d["Y"]
        return self.encoder.encode(d)

    # def hash(self, rehash=False):
    #     if(self.hashcode == None):
    #         self.hashcode = compute_hash(self.to_json())
    #     return self.hashcode

    def write(self, verbose=0):
        '''Write the json string for the procedure to its directory'''
        json_str = self.to_json()
        hashcode = compute_hash(json_str)
        blob_path = self.get_path()
        write_object(blob_path, 'procedure.json', json_str, verbose=verbose)

    def is_archived(self):
        '''Returns True if this procedure is already archived'''
        blob_path = get_blob_path(self, self.archive_dir)
        data_path = blob_path+"archive.h5"
        if(os.path.exists(data_path)):
            return True
        else:
            return False

    def archive(self):
        '''Store the DataProcedure in a directory computed by its hashcode'''
        if((self.X is None or self.Y is None) == False):
            blob_path = self.get_path()
            if( os.path.exists(blob_path) == False):
                os.makedirs(blob_path)
            if( os.path.exists(blob_path + 'procedure.json') == False):
                self.write()
            X = self.X
            Y = self.Y

            if(isinstance(self.X, list) == False): X = [X]
            if(isinstance(self.Y, list) == False): Y = [Y]
            h5f = h5py.File(self.get_path() + 'archive.h5', 'w')
            h5f.create_group("X")
            for i, x in enumerate(X):
                h5f.create_dataset('X/'+str(i), data=x)
            h5f.create_group("Y")
            for i, y in enumerate(Y):
                h5f.create_dataset('Y/'+str(i), data=y)
            
            h5f.close()
            data_archive = DataProcedure.read_record(self.archive_dir)

            #TODO: this is a really backward way of doing this
            jstr = self.to_json()
            d = json.loads(jstr)

            # print(d)
            proc_dict = {}
            proc_dict['func'] = d['func']
            proc_dict['module'] = d['func_module']
            proc_dict['args'] = d['args']
            proc_dict['kargs'] = d['kargs']
            data_archive[self.hash()] = proc_dict

            DataProcedure.write_record(data_archive, self.archive_dir)
            # def read_json_obj(directory, filename, verbose=0):
                
        else:
            raise ValueError("Cannot archive DataProcedure with NoneType X or Y")
        


        # self.to_record({'name' : self.name}, append=True)

    def remove_from_archive(self):
        '''Removes the DataProcedure from the data_archive and destroys its blob directory'''
        data_archive = DataProcedure.read_record(self.archive_dir)
        if(self.hash() in  data_archive): del data_archive[self.hash()] 
        DataProcedure.write_record(data_archive, self.archive_dir)

        Storable.remove_from_archive(self)

    def getData(self, archive=True, redo=False, verbose=1):
        '''Apply the DataProcedure returning X,Y from the archive or generating them from func'''

        if(self.is_archived() and redo == False):
            h5f = None
            try:
                h5f = h5py.File(self.get_path() + 'archive.h5', 'r')
                self.X = []
                X_group = h5f['X']
                keys = list(X_group.keys())
                keys.sort()
                for key in keys:
                    self.X.append(X_group[key][:])

                self.Y = []
                Y_group = h5f['Y']
                keys = list(Y_group.keys())
                keys.sort()
                for key in keys:
                    self.Y.append(Y_group[key][:])

                h5f.close()

                out = (self.X, self.Y)

                if(verbose >= 1): print("DataProcedure results %r read from archive" % self.hash())
            except:
                if(h5f != None): h5f.close()
                if(verbose >= 1): print("Failed to load archive %r running from scratch" % self.hash())
                return self.getData(archive=archive, redo=True, verbose=verbose)
        else:
            prep_func = self.get_func(self.func, self.func_module)

            out = prep_func(*self.args, **self.kargs)
            

            if(isinstance(out, tuple)):
                if(len(out) == 2):
                    if( (isinstance(out[0], list) or isinstance(out[0], np.ndarray)) 
                        and (isinstance(out[1], list) or isinstance(out[1], np.ndarray))):
                        self.X, self.Y = out
                else:
                    raise ValueError("getData returned too many arguments expected 2 got %r" % len(out))
            elif(isinstance(out, types.GeneratorType)):
                    print("GOT GENTYPE")
                    self.archive_getData = False
                    archive = False
            else:
                raise ValueError("getData did not return (X,Y) or Generator got types (%r,%r)"
                                    % ( type(out[0]), type(out[1]) ))

            
            # print("WRITE:", self.X.shape, self.Y.shape)
            print(self.archive_getData == True, archive == True)
            if(self.archive_getData == True or archive == True): self.archive()
        return out

    def get_summary(self):
        '''Get the summary for the DataProcedure as a string'''
        str_args = ','.join([str(x) for x in self.args])
        str_kargs = ','.join([str(x) + "=" + str(self.kargs[x]) for x in self.kargs])
        arguments = ','.join([str_args, str_kargs])
        return self.func_module + "." + self.func +"(" + arguments + ")"
    def summary(self):
        '''Print a summary'''
        print("-"*50)
        print("DataProcedure (%r)" % self.hash())
        print("    " + self.get_summary())
        print("-"*50) 

    @staticmethod
    def get_func(name, module):
        '''Get a function from its name and module path'''
        # print("from " + module +  " import " + name + " as prep_func")
        try:
            exec("from " + module +  " import " + name + " as prep_func")
        except ImportError:
            # try:
            #     exec('prep_func = ' + name)
            # except Exception:
            raise ValueError("DataProcedure function %r does not exist in %r. \
                For best results functions should be importable and not locally defined." % (str(name), str(module)))
        return prep_func

    @classmethod
    def from_json(cls, archive_dir ,json_str, arg_decode_func=None):  
        '''Get a DataProcedure object from its json string'''
        d = json.loads(json_str)
        func = None
        temp = lambda x: 0
        try:
            func = cls.get_func(d['func'], d['func_module'])
        except ValueError:
            func = temp
        args, kargs = d['args'], d['kargs']
        for i,arg in enumerate(args):
            islist = True
            if(isinstance(arg, list) == False):
                islist = False
                arg = [arg]
            for j ,a in enumerate(arg):
                if(isinstance(a, str) or isinstance(a, unicode)):
                    obj = json.loads(a)
                    if(isinstance(obj, dict)):
                        # print(type(a), type(obj))
                        if(obj.get('class_name', None) == "DataProcedure"):
                            arg[j] = DataProcedure.from_json(archive_dir, a,arg_decode_func)
            if(islist == False):
                arg = arg[0]
            args[i] = arg
        if(arg_decode_func != None):
            # print('arg_decode_func_ENABLED:', arg_decode_func.__name__)
            args, kargs = arg_decode_func(*args, **kargs)

        archive_getData = d['archive_getData']
        dp = cls(archive_dir, archive_getData, func, *args, **kargs)
        if(func == temp):
            dp.func = d['func']
            dp.func_module = d['func_module']
        return dp

    @staticmethod
    def find_by_hashcode( hashcode, archive_dir, verbose=0 ):
        '''Returns the archived DataProcedure with the given hashcode or None if one is not found'''
        path = get_blob_path(hashcode, archive_dir) + 'procedure.json'
        try:
            f = open( path, "rb" )
            json_str = f.read()
            f.close()
            # print(json_str)
            out = DataProcedure.from_json(archive_dir,json_str)
            if(verbose >= 1): print('Sucessfully loaded procedure.json at ' + archive_dir)
        except (IOError, EOFError):
            out = None
            if(verbose >= 1): print('Failed to load procedure.json  at ' + archive_dir)
        return out

    @staticmethod
    def read_record(archive_dir, verbose=0):
        '''Returns the record read from the trial directory'''
        return read_json_obj(archive_dir, 'data_record.json')

    @staticmethod
    def write_record(record,archive_dir, verbose=0):
        '''Writes the record to the trial directory'''
        write_json_obj(record, archive_dir, 'data_record.json')




class KerasTrial(Storable):
    '''An archivable object representing a machine learning trial in keras'''
    def __init__(self,
                    archive_dir,
                    name = 'trial',
    				model=None,
                    train_procedure=None,
                    samples_per_epoch=None,
                    validation_split=0.0,
                    val_procedure=None,
                    nb_val_samples=None,

                    optimizer=None,
                    loss=None,
                    metrics=[],
                    sample_weight_mode=None,
                    batch_size=32,
                    nb_epoch=10,
                    callbacks=[],
                    
                    max_q_size=None,
                    nb_worker=None,
                    pickle_safe=False,

                    shuffle=True,
                    class_weight=None,
                    sample_weight=None
                ):
    	
        Storable.__init__(self)
        if(archive_dir[len(archive_dir)-1] != "/"):
            archive_dir = archive_dir + "/"
        self.archive_dir = archive_dir
        self.name = name
        self.setModel(model)

        self.setTrain(train_procedure=train_procedure,samples_per_epoch=samples_per_epoch)

        self.setValidation(validation_split=validation_split,val_procedure=val_procedure,nb_val_samples=nb_val_samples)

        self.setCompilation(optimizer=optimizer,
                                loss=loss,
                                metrics=metrics,
                                sample_weight_mode=sample_weight_mode)


        self.setFit(    batch_size=batch_size,
                        nb_epoch=nb_epoch,
                        callbacks=callbacks,
                        shuffle=shuffle,
                        class_weight=class_weight,
                        sample_weight=sample_weight)

        self.setFit_Generator(  nb_epoch=nb_epoch,
                                callbacks=callbacks,
                                class_weight=class_weight,
                                max_q_size=max_q_size,
                                nb_worker=nb_worker,
                                pickle_safe=pickle_safe)
    

    def setModel(self, model):
        '''Set the model used by the trial (either the object or derived json string)'''
        self.model = model
        self.compiled_model = None
        if(isinstance(model, Model)):
            self.model = model.to_json()

    def _prep_procedure(self, procedure, name='train'):
        if(procedure != None):
            if(isinstance(procedure, list) == False):
                procedure = [procedure]
            l = []
            for p in procedure:
                if(isinstance(p, DataProcedure)):
                    l.append(p.to_json())
                elif(isinstance(p, str) or isinstance(p, unicode)):
                    l.append(p)
                else:
                    raise TypeError("%r_procedure must be DataProcedure, but got %r" % (name,type(p)))
            return l
        else:
            return None

    def setTrain(self,
                   train_procedure=None, samples_per_epoch=None):
        '''Sets the training data for the trial'''
        self.train_procedure = self._prep_procedure(train_procedure, 'train')
        self.samples_per_epoch = samples_per_epoch
    
    def setValidation(self,
                  val_procedure=None, validation_split=0.0, nb_val_samples=None):
        '''Sets the training data for the trial'''
        # if(isinstance(val_procedure, list) and len(val_procedure) == 1):
        #     val_procedure = val_procedure[0]
        # if((isinstance(val_procedure, DataProcedure) or val_procedure is None) == False):
        #     raise TypeError("val_procedure must have type DataProcedure, but got list %r" % type(val_procedure))
        if(isinstance(val_procedure, float)):
            validation_split = val_procedure
            val_procedure = None
        if(isinstance(validation_split, float) == False):
            raise TypeError("validation_split must have type float, but got %r" % type(validation_split))
        if((isinstance(nb_val_samples, int) or nb_val_samples is None) == False):
            raise TypeError("nb_val_samples must have type int, but got %r" % type(nb_val_samples))
        # if(isinstance(val_procedure, float)):
        #     self.validation_split = val_procedure
        #     self.val_procedure = None
        # else:
        #     self.validation_split = 0.0
        #     self.val_procedure = self._prep_procedure(val_procedure)
        self.validation_split = validation_split
        self.val_procedure = self._prep_procedure(val_procedure, 'val')
        self.nb_val_samples = nb_val_samples

    def setCompilation(self,
    				optimizer,
                    loss,
                    metrics=[],
                    sample_weight_mode=None):
        '''Sets the compilation arguments for the trial'''
        metrics.sort()
        self.optimizer=optimizer
        self.loss=loss
        self.metrics=metrics
        self.sample_weight_mode=sample_weight_mode

    def setFit(self,
                batch_size=32,
                nb_epoch=10,
                callbacks=[],
                shuffle=True,
                class_weight=None,
                sample_weight=None):
        '''Sets the fit arguments for the trial'''
    	#Fit
        strCallbacks = []
        for c in callbacks:
            if(isinstance(c, SmartCheckpoint) == False):
                if(isinstance(c, Callback) == True):
                    strCallbacks.append(encodeCallback(c))
                else:
                    strCallbacks.append(c)
        callbacks = strCallbacks

        self.batch_size=batch_size
        self.nb_epoch=nb_epoch
        self.callbacks=callbacks
        # self.validation_split=validation_split
        # self.validation_data=validation_data
        self.shuffle=shuffle
        self.class_weight=class_weight
        self.sample_weight=sample_weight

    def setFit_Generator(self,
                nb_epoch=10,
                callbacks=[],
                class_weight=True,
                max_q_size=None,
                nb_worker=None,
                pickle_safe=False):
        '''Sets the fit arguments for the trial'''
        #Fit
        strCallbacks = []
        for c in callbacks:
            if(isinstance(c, SmartCheckpoint) == False):
                if(isinstance(c, Callback) == True):
                    strCallbacks.append(encodeCallback(c))
                else:
                    strCallbacks.append(c)
        callbacks = strCallbacks

        # self.samples_per_epoch=samples_per_epoch
        self.nb_epoch=nb_epoch
        self.callbacks=callbacks
        # self.validation_data=validation_data
        # self.nb_val_samples=nb_val_samples
        self.class_weight=class_weight
        self.max_q_size=max_q_size
        self.nb_worker=nb_worker
        self.pickle_safe=pickle_safe

    def to_json(self):
        '''Converts the trial to a json string '''
        encoder = TrialEncoder()
        return encoder.encode(self)
    

    # def preprocess(self):
    #     return preprocessFromPandas_label_dir_pairs(
    #             label_dir_pairs=self.label_dir_pairs,
    #             num_samples=self.num_samples,
    #             object_profiles=self.object_profiles,
    #             observ_types=self.observ_types)
    def compile(self, loadweights=False, redo=False, custom_objects={}):
        '''Compiles the model set for this trial'''
        if(self.compiled_model is None or redo): 
            model = self.get_model(loadweights=loadweights, custom_objects=custom_objects)#model_from_json(self.model)
            model.compile(
                optimizer=self.optimizer,
                loss=self.loss,
                metrics=self.metrics,
                sample_weight_mode=self.sample_weight_mode)
            self.compiled_model = model
        else:
            model = self.compiled_model
        return model

    def _generateCallbacks(self, verbose):
        callbacks = []
        for c in self.callbacks:
            if(c != None):
                callbacks.append(decodeCallback(c))
        monitor = 'val_acc'
        if(self.validation_split == 0.0 or self.val_procedure is None):
            monitor = 'acc'
        callbacks.append(SmartCheckpoint('weights', associated_trial=self,
                                             monitor=monitor,
                                             verbose=verbose,
                                             save_best_only=True,
                                             mode='auto'))
        return callbacks

    def _history_to_record(self, record_store):
        histDict = self.get_history()
        if(histDict != None):
            dct = {} 
            for x in record_store:
                if(histDict.get(x, None) is None):
                    continue
                dct[x] = max(histDict[x])
            self.to_record(dct)

    def fit(self, model, x_train, y_train, record_store=["val_acc"], verbose=1):
        '''Runs model.fit(x_train, y_train) for the trial using the arguments passed to trial.setFit(...)'''
        
        # print(self.callbacks)
        callbacks = self._generateCallbacks(verbose)

        model.fit(x_train, y_train,
            batch_size=self.batch_size,
            nb_epoch=self.nb_epoch,
            verbose=verbose,
            callbacks=callbacks,
            validation_split=self.validation_split,
            #validation_data=self.validation_data,
            shuffle=self.shuffle,
            class_weight=self.class_weight,
            sample_weight=self.sample_weight)
        self._history_to_record(record_store)
       

    def fit_generator(self, model, generator, validation_data=None, record_store=["val_acc"] ,verbose=1):

        callbacks = self._generateCallbacks(verbose)

        model.fit_generator(generator, self.samples_per_epoch,
                    nb_epoch=self.nb_epoch,
                    verbose=verbose,
                    callbacks=callbacks,
                    validation_data=validation_data,
                    nb_val_samples=self.nb_val_samples)
#                      validation_data=None, nb_val_samples=None,
#                      class_weight={}, max_q_size=10, nb_worker=1, pickle_safe=False):
        self._history_to_record(record_store)


    def write(self, verbose=0):
        '''Writes the model's json string to its archive location''' 
        json_str = self.to_json()
        hashcode = compute_hash(json_str)
        blob_path = self.get_path()
        write_object(blob_path, 'trial.json', json_str, verbose=verbose)

        self.to_record({'name' : self.name}, append=True)
                 

    def execute(self, archiveTraining=True, archiveValidation=True, train_arg_decode_func=None, val_arg_decode_func=None, custom_objects={}):
        '''Executes the trial, fitting on the X, and Y for training for each given DataProcedure in series'''
    	if(self.train_procedure is None):
            raise ValueError("Cannot execute trial without DataProcedure")
        if(self.is_complete() == False):
            model = self.compile(custom_objects=custom_objects)
            train_procs = self.train_procedure
            if(isinstance(train_procs, list) == False): train_procs = [train_procs]
            # print(train_procs)
            totalN = 0
            if(self.val_procedure != None):
                if(len(self.val_procedure) != 1):
                    raise ValueError("val_procedure must be single procedure, but got list")
                val_proc = DataProcedure.from_json(self.archive_dir,self.val_procedure[0], arg_decode_func=val_arg_decode_func)
                val = val_proc.getData(archive=archiveValidation)
            else:
                val = None


            for p in train_procs:
                train_proc = DataProcedure.from_json(self.archive_dir,p, arg_decode_func=train_arg_decode_func)

                

                train = train_proc.getData(archive=archiveTraining)

                if(isinstance(train, types.GeneratorType)):
                    self.fit_generator(model,train, val)
                    totalN += self.samples_per_epoch
                elif(isinstance(train, tuple)):
                    if(isinstance(val,  types.GeneratorType)):
                        raise ValueError("Fit() cannot take generator for validation_data. Try fit_generator()")
                    X,Y = train
                    if(isinstance(X, list) == False): X = [X]
                    if(isinstance(Y, list) == False): Y = [Y]
                    totalN += Y[0].shape[0]
                    self.fit(model,X, Y)
                else:
                    raise ValueError("Traning DataProcedure returned useable type %r" % type(train))
            self.write()

            # if(self.validation_split != 0.0):
            dct =  {'num_train' : totalN*(1.0-self.validation_split),
                    'num_validation' : totalN*(self.validation_split),
                    'elapse_time' : self.get_history()['elapse_time'],
                    'fit_cycles' : len(train_procs)
                    }
            self.to_record( dct, replace=True)
        else:
            print("Trial %r Already Complete" % self.hash())
    def test(self,test_proc, test_samples=None, archiveTraining=True, custom_objects={}, max_q_size=10, nb_worker=1, pickle_safe=False, arg_decode_func=None):
        model = self.compile(custom_objects=custom_objects)
        if(isinstance(test_proc, list) == False): test_proc = [test_proc]
        # test_proc = self._prep_procedure(test_proc)

        sum_metrics = []
        for p in test_proc:
            if(isinstance(p, str) or isinstance(p, unicode)):
                p = DataProcedure.from_json(self.archive_dir,p, arg_decode_func=arg_decode_func)
            elif(isinstance(p, DataProcedure) == False):
                 raise TypeError("test_proc expected DataProcedure, but got %r" % type(test_proc))

            test_data = p.getData(archive=archiveTraining)
            n_samples = 0
            if(isinstance(test_data, types.GeneratorType)):
                metrics = model.evaluate_generator(test_data, test_samples)
#                                                    max_q_size=max_q_size,
#                                                    nb_worker=nb_worker,
#                                                    pickle_safe=pickle_safe)
                n_samples = test_samples
            else:
                X,Y = test_data
                if(isinstance(X, list) == False): X = [X]
                if(isinstance(Y, list) == False): Y = [Y]
                metrics = model.evaluate(X, Y)
                n_samples = Y[0].shape[0]
            if(sum_metrics == []):
                sum_metrics = metrics
            else:
                sum_metrics = [sum(x) for x in zip(sum_metrics, metrics)]
        metrics = [x/len(test_proc) for x in sum_metrics]

        self.to_record({'test_loss' : metrics[0], 'test_acc' :  metrics[1], 'num_test' : n_samples}, replace=True)
        return metrics

    def to_record(self, dct, append=False, replace=True):
        '''Pushes a dictionary of values to the archive record for this trial'''
        record = self.read_record(self.archive_dir)
        hashcode = self.hash()
        trial_dict = record.get(hashcode, {})
        for key in dct:
            if(append == True):
                if((key in trial_dict) == True):
                    x = trial_dict[key]
                    if(isinstance(x, list) == False):
                        x = [x]
                    if(replace == True):
                        x = set(x)
                        x.add(dct[key])
                        x = list(x)
                    else:
                        x.append(dct[key])
                    trial_dict[key] = x
                else:
                    trial_dict[key] = dct[key]
            else:
                if(replace == True or (key in trial_dict) == False):
                    trial_dict[key] = dct[key]
        record[hashcode] = trial_dict
        self.write_record(record, self.archive_dir) 

    def get_record_entry(self, verbose=0):
        '''Get the dictionary containing all the record values for this trial '''
        record = self.read_record(self.archive_dir, verbose=verbose)
        return record.get(self.hash(), None)

    def get_from_record(self, keys, verbose=0):
        '''Get a value from the record '''
        recordDict = self.get_record_entry(verbose=verbose)
        if(isinstance(keys, list)):
            out = []
            for key in keys:
                out.append(recordDict.get(key, None))
        else:
            out = recordDict.get(keys, None)
        return out

    def get_history(self, verbose=0):
        '''Get the training history for this trial'''
        # history_path = self.get_path()+"history.json"
        history = read_json_obj(self.get_path(), "history.json")
        if(history == {}):
            history = None
        return history

    def get_model(self, loadweights=False,custom_objects={}):
        '''Gets the model, optionally with the best set of weights'''
        model = model_from_json(self.model, custom_objects=custom_objects)
        if(loadweights): model.load_weights(self.get_path()+"weights.h5")
        return model

    def is_complete(self):
        '''Return True if the trial has completed'''
        blob_path = get_blob_path(self, self.archive_dir)
        history_path = blob_path+"history.json"
        if(os.path.exists(history_path)):

            histDict = json.load(open( history_path, "rb" ))
            if(len(histDict.get('stops', [])) > 0):
                return True
            else:
                return False
        else:
            return False


    def summary(self,
                showName=False,
                showDirectory=False,
                showRecord=True,
                showTraining=True,
                showValidation=True,
                showCompilation=True,
                showFit=True,
                showModelPic=False,
                showNoneType=False,
                squat=True):
        '''Print a summary of the trial
            #Arguments:
                showName=False,showDirectory=False, showRecord=True, showTraining=True, showCompilation=True, showFit=True,
                 showModelPic=False, showNoneType=False -- Control what data is printed
                squat=True -- If False shows data on separate lines
        '''
        indent = "    "     
        d = self.__dict__
        def _listIfNotNone(keys):
            l = []
            for key in keys:
                if(showNoneType == False):
                    val = d.get(key, None)
                    if(val != None):
                        # print(indent*2 + )
                        l.append(str(key) + "=" + str(val))
            return l
        if(squat):
            sep = ", "         
        else:
            sep = "\n" + indent*2 

        print("-"*50)
        print("TRIAL SUMMARY (" + self.hash() + ")" )
        if(showDirectory):print(indent + "Directory: " + self.archive_dir)
        if(showName):  print(indent + "Name: " + self.name)
            # n = self.get_from_record(['name'])
           

        if(showRecord):
            print(indent + "Record_Info:")
            #try:
            record = self.get_record_entry()
            #except KeyError as e:
                
            if(record != None):
                records = []
                for key in record:
                    records.append(str(key) + " = " + str(record[key]))
                records.sort()
                print(indent*2 + sep.join(records))
            else:
                print(indent*2 + "No record. Not stored in archive.")

        if(showTraining):
            print(indent + "Training:")
            preps = []
            for s in self.train_procedure:
                p = DataProcedure.from_json(self.archive_dir, s)
                preps.append(p.get_summary())
            print(indent*2 + sep.join(preps))
            if(self.samples_per_epoch != None):
                print(indent*2 + "samples_per_epoch = %r" % self.samples_per_epoch)

        if(showValidation):
            print(indent + "Validation:")
            if(self.val_procedure == None):
                print(indent*2 + "validation_split = %r" % self.validation_split)
            else:
                preps = []
                for s in self.val_procedure:
                    p = DataProcedure.from_json(self.archive_dir, s)
                    preps.append(p.get_summary())
                print(indent*2 + sep.join(preps))
                if(self.nb_val_samples != None):
                    print(indent*2 + "nb_val_samples = %r" % self.nb_val_samples)

        if(showCompilation):
            print(indent + "Compilation:")
            comps = _listIfNotNone(["optimizer", "loss", "metrics", "sample_weight_mode"])
            print(indent*2 + sep.join(comps))

        if(showFit):
            print(indent + "Fit:")
            fits = _listIfNotNone(["batch_size", "nb_epoch", "verbose", "callbacks",
                                     "validation_split", "validation_data", "shuffle",
                                     "class_weight", "sample_weight"])
            print(indent*2 + sep.join(fits))

        # if(showModelPic):

        print("-"*50)

    def remove_from_archive(self):
        '''Remove the trial from the record and destroys its archive including the trial.json, weights.h5 and history.json'''
        record = self.read_record(self.archive_dir)
        if(self.hash() in  record): del record[self.hash()] 
        self.write_record(record, self.archive_dir)

        Storable.remove_from_archive(self)


    @classmethod
    def from_json(cls,archive_dir,json_str, name='trial'):
        '''Reconsitute a KerasTrial object from its json string'''
        d = json.loads(json_str)
        # print(d['callbacks'])
        trial = cls(
                archive_dir,
                name = name,
                model = d.get('model', None),
                train_procedure=d.get('train_procedure', None),
                samples_per_epoch=d.get('samples_per_epoch', None),
                validation_split=d.get('validation_split', 0.0),
                val_procedure=d.get('val_procedure', None),
                nb_val_samples=d.get('nb_val_samples', None),

                optimizer=d.get('optimizer', None),
                loss=d.get('loss', None),
                metrics=d.get('metrics', []),
                sample_weight_mode=d.get('sample_weight_mode', None),
                batch_size=d.get('batch_size', 32),
                nb_epoch=d.get('nb_epoch', 10),
                callbacks=d.get('callbacks', []),

                max_q_size=d.get('max_q_size', True),
                nb_worker=d.get('nb_worker', None),
                pickle_safe=d.get('pickle_safe', None),

                shuffle=d.get('shuffle', True),
                class_weight=d.get('class_weight', None),
                sample_weight=d.get('sample_weight', None))
        return trial
         
    @classmethod
    def find_by_hashcode(cls, hashcode, archive_dir, verbose=0 ):
        '''Returns the archived KerasTrial with the given hashcode or None if one is not found'''
        path = get_blob_path(hashcode, archive_dir) + 'trial.json'
        try:
            f = open( path, "rb" )
            json_str = f.read()
            f.close()
            # print(json_str)
            out = cls.from_json(archive_dir,json_str)
            if(verbose >= 1): print('Sucessfully loaded trial.json at ' + archive_dir)
        except (IOError, EOFError):
            out = None
            if(verbose >= 1): print('Failed to load trial.json  at ' + archive_dir)
        return out

    @staticmethod
    def read_record(archive_dir, verbose=0):
        '''Returns the record read from the trial directory'''
        return read_json_obj(archive_dir, 'trial_record.json')

    @staticmethod
    def write_record(record,archive_dir, verbose=0):
        '''Writes the record to the trial directory'''
        write_json_obj(record, archive_dir, 'trial_record.json')

class TrialEncoder(json.JSONEncoder):
    '''A json encoder for KerasTrials. Doesn't store name,archive_dir,hashcode etc since they don't affect how it functions'''
    def __init__(self):
        json.JSONEncoder.__init__(self,sort_keys=True, indent=4)
    def default(self, obj):
        temp = obj.compiled_model
        obj.compiled_model = None
        d = obj.__dict__
        d = copy.deepcopy(d)
        if('name' in d): del d['name']
        if('archive_dir' in d): del d['archive_dir']
        if('hashcode' in d): del d['hashcode']
        if('compiled_model' in d): del d['compiled_model']
        obj.compiled_model = temp
        return d


#TODO: Stopping Callbacks can't infer mode -> only auto works
def encodeCallback(c):
    '''Encodes callbacks so that they can be decoded later'''
    d = {}
    if(isinstance(c, EarlyStopping)):
        d['monitor'] = c.monitor
        d['patience'] = c.patience
        d['verbose'] = c.verbose
        d['mode'] = 'auto'
        if(isinstance(c, OverfitStopping)):
            d['type'] = "OverfitStopping"
            d['comparison_monitor'] = c.comparison_monitor
            d['max_percent_diff'] = c.max_percent_diff
        else:
            d['type'] = "EarlyStopping"
    return d




def decodeCallback(d):
    '''Decodes callbacks into usable objects'''
    # if(d == None):
    # print(d)
    if(d['type'] == "OverfitStopping"):
        return OverfitStopping(  monitor=d['monitor'],
                                comparison_monitor=d['comparison_monitor'],
                                max_percent_diff=d['max_percent_diff'],
                                patience=d['patience'],
                                verbose=d['verbose'],
                                mode =d['mode'])
    elif(d['type'] == "EarlyStopping"):
        return EarlyStopping(   monitor=d['monitor'],
                                patience=d['patience'],
                                verbose=d['verbose'],
                                mode =d['mode'])



def compute_hash(inp):
    '''Computes a SHA1 hash string from a json string or Storable'''
    json_str = inp
    if(isinstance(inp, Storable)):
        json_str = inp.to_json()
    h = hashlib.sha1()
    h.update(json_str)
    return h.hexdigest()

def split_hash(hashcode):
    '''Splits a SHA1 hash string into two strings. One with the first 5 characters and another with the rest'''
    return hashcode[:5], hashcode[5:]

def get_blob_path(*args, **kwargs):
    '''Blob path (archive location) from either (storable,archive_dir), (hashcode, archive_dir), or
        (json_str=?, archive_dir=?)'''
    def _helper(a):
        if(isinstance(a, Storable)):
            return split_hash(a.hash())
        elif(isinstance(a, str) or isinstance(a, unicode)):
            hashcode = a
            return split_hash(hashcode)
        else:
            raise ValueError("Unknown datatype at 1st argument")
    if(len(args) == 2):
        blob_dir, blob = _helper(args[0])
        archive_dir = args[1]
    elif(len(args) <= 1):
        if('archive_dir' in kwargs):
            archive_dir = kwargs['archive_dir']
        else:
            raise ValueError("Trial Directory was not specified")
        if(len(args) == 1):
            blob_dir, blob = _helper(args[0])
        elif(len(args) == 0):
            if 'json_str' in kwargs:
                hashcode = compute_hash(kwargs['json_str'])
            elif 'hashcode' in kwargs:
                hashcode = kwargs['hashcode']
            else:
                raise ValueError("No hashcode or trial specified")
            blob_dir, blob = split_hash(hashcode)
    else:
        raise ValueError("Too Many arguments")

    blob_path = archive_dir + "blobs/" +  blob_dir + '/' + blob + "/"
    return blob_path


def read_dataArchive(archive_dir, verbose=0):
    '''Returns the data archive read from the trial directory'''
    return read_json_obj(archive_dir, 'data_archive.json')
def write_dataArchive(data_archive, archive_dir, verbose=0):
    '''Writes the data archive to the trial directory'''
    write_json_obj(data_archive, archive_dir, 'data_archive.json')




def read_json_obj(directory, filename, verbose=0):
    '''Return a json object read from the given directory'''
    try:
        obj = json.load(open( directory + filename, "rb" ))
        if(verbose >= 1): print('Sucessfully loaded ' + filename +'  at ' + directory)
    except (IOError, EOFError):
        obj = {}
        if(verbose >= 1): print('Failed to load '+ filename +'  at ' + directory)
    return obj

def write_json_obj(obj,directory, filename, verbose=0):
    '''Writes a json object to the given directory'''
    try:
        json.dump(obj,  open( directory + filename, "wb" ))
        if(verbose >= 1): print('Sucessfully wrote ' + filename +'  at ' + directory)
    except (IOError, EOFError):
        if(verbose >= 1): print('Failed to write '+ filename +'  at ' + directory)



def write_object(directory, filename, data, verbose=0):
    '''Writes an object from the given data with the given filename in the given directory'''
    if not os.path.exists(directory):
        os.makedirs(directory)
    path = directory + filename
    try:
        f = open(path, 'w')
        f.write(data)
        if(verbose >= 1): print('Sucessfully wrote %r at %r' + (filename, directory))
    except (IOError, EOFError):
        if(verbose >= 1): print('Failed to write %r at %r' + (filename, directory))
    f.close()





#Reading Trials

def get_all_data(archive_dir):
    '''Gets all the DataProcedure in the data_archive'''
    return get_data_by_function('.', archive_dir)

def get_data_by_function(func, archive_dir):
    '''Gets a list of DataProcedure that use a certain function'''
    data_archive = DataProcedure.read_record(archive_dir)
    out = []
    if(isinstance(func, str)):
        func_name = func
        func_module = None
    else:
        func_name = func.__name__
        func_module = func.__module__

    # print(func_name, func_module)
    # print(len(data_archive))
    for key in data_archive:
        t_func = data_archive[key].get("func", 'unknown')
        t_module = data_archive[key].get("func_module", 'unknown')
        # print(t_func, t_module)
        # print(data_archive)
        # print(t_name, name.decode("UTF-8"))
        # print([re.match(name, x) for x in t_name])
        if(re.match(func_name, t_func) != None and (func_module is None or re.match(func_module, t_module) != None)):
            # blob_path = get_blob_path(key, archive_dir)
            dp = DataProcedure.find_by_hashcode(key, archive_dir)
            if(dp != None):
                out.append(dp)

    return out


def get_all_trials(archive_dir):
    '''Get all the trials listed in the trial_record'''
    return get_trials_by_name('.', archive_dir)

def get_trials_by_name(name, archive_dir):
    '''Get all the trials with a particluar name or that match a given regular expression'''
    record = KerasTrial.read_record(archive_dir)
    out = []
    for key in record:
        t_name = record[key].get("name", 'unknown')
        # print(t_name, name.decode("UTF-8"))
        if(isinstance(t_name, list) == False):
            t_name = [t_name]
        # print([re.match(name, x) for x in t_name])
        if True in [re.match(name, x) != None for x in t_name]:
            # blob_path = get_blob_path(key, archive_dir)
            dp = KerasTrial.find_by_hashcode(key, archive_dir)
            if(dp != None):
                out.append(dp)

    return out

