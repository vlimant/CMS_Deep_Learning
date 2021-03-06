import sys

if __package__ is None:
    import sys, os
    sys.path.append(os.path.realpath("/data/shared/Software/"))
    sys.path.append(os.path.realpath("../"))
p = "/home/dweitekamp/mpi_learn/"
if(not p in sys.path):
    sys.path.append(p)

from CMS_Deep_Learning.utils.deepconfig import deepconfig
deepconfig("cpu", backend="theano")

from CMS_Deep_Learning.preprocessing.preprocessing import *
from CMS_Deep_Learning.storage.MPIArchiving import *
from CMS_Deep_Learning.postprocessing.analysistools import findsubsets

from keras.models import Model
from keras.layers import Dense, Dropout, merge, Input, LSTM, Masking
from keras.callbacks import EarlyStopping

#The observables taken from the table
DEFAULT_OBSV_TYPES = ['E/c', 'Px', 'Py', 'Pz', 'PT_ET','Eta', 'Phi', 'Charge', 'X', 'Y', 'Z',\
                     'Dxy', 'Ehad', 'Eem', 'MuIso', 'EleIso', 'ChHadIso','NeuHadIso','GammaIso', "ObjType"]


DEFAULT_LABEL_DIR_PAIRS = \
            [   ("qcd", "/data/shared/Delphes/qcd_lepFilter_13TeV/pandas_h5/"),
                ("ttbar", "/data/shared/Delphes/ttbar_lepFilter_13TeV/pandas_h5/"),
                ("wjet", "/data/shared/Delphes/wjets_lepFilter_13TeV/pandas_h5/")

            ]
def genModel(name,object_profiles,out_dim, depth, vecsize
            ,lstm_activation="relu", lstm_dropout = 0.0, dropout=0.0,output_activation="softmax", single_list=False):
    inputs = []
    if(single_list):
        a = Input(shape=(sum([p.max_size for p in object_profiles]) , vecsize), name="input")
        inputs.append(a)
    else:
        mergelist = []
        for i, profile in enumerate(object_profiles):
            inp = a = Input(shape=(profile.max_size , vecsize), name="input_" + str(i))
            inputs.append(inp)
            mergelist.append(a)
        a = merge(mergelist, mode='concat', concat_axis=1, name="merge")
    for i in range(depth):
        a = Masking(mask_value=0.0)(a)
        a = LSTM(vecsize,
                 input_shape=(None,vecsize),
                 dropout_W=lstm_dropout,
                 dropout_U=lstm_dropout,
                 activation=lstm_activation,
                 name = "lstm_" +str(i))(a)
        if(dropout > 0.0):
            a =  Dropout(dropout, name="dropout_"+str(i))(a)
    dense_out = Dense(out_dim, activation=output_activation, name='main_output')(a)
    model = Model(input=inputs, output=dense_out, name=name)
    return model

def runTrials(archive_dir,
                workers,
                observ_types=DEFAULT_OBSV_TYPES,
                label_dir_pairs=DEFAULT_LABEL_DIR_PAIRS,
                epochs = 30,
                batch_size = 100,
                patience = 8,
                num_val = 20000,
                num_train = 75000,
                output_activation = "softmax",
                loss='categorical_crossentropy',
                optimizer_options = ['rmsprop','adam'],
                sortings = [("Phi", False),("Eta", False), ("PT_ET", False), ("PT_ET", True), (None,False)],
                single_list_options = [False]#[True, False]
                ):
    vecsize = len(observ_types)
    ldpsubsets = [sorted(list(s)) for s in findsubsets(label_dir_pairs)]
    #Make sure that we do 3-way classification as well
    ldpsubsets.append(sorted(label_dir_pairs))
    #archive_dir = "/data/shared/Delphes/keras_archive/"

    earlyStopping = EarlyStopping(verbose=1, patience=patience)
    trial_tups = []
    print(archive_dir, workers)
    # Loop over all subsets
    print(ldpsubsets)
    for ldp in ldpsubsets:
        labels = [x[0] for x in ldp]
        for sort_on, sort_ascending in sortings:
            sort_on = [sort_on]
            for single_list in single_list_options:

                object_profiles = [
                    ObjectProfile("Electron", 8, pre_sort_columns=["PT_ET"], pre_sort_ascending=False, sort_columns=[sort_on],
                                  sort_ascending=sort_ascending, addColumns={"ObjType": 1}),
                    ObjectProfile("MuonTight", 8, pre_sort_columns=["PT_ET"], pre_sort_ascending=False, sort_columns=[sort_on],
                                  sort_ascending=sort_ascending, addColumns={"ObjType": 2}),
                    # ObjectProfile("Photon", -1, pre_sort_columns=["PT_ET"], pre_sort_ascending=False, sort_columns=[sort_on], sort_ascending=False, addColumns={"ObjType":3}),
                    ObjectProfile("MissingET", 1, addColumns={"ObjType": 4}),
                    ObjectProfile("EFlowPhoton", 100, pre_sort_columns=["PT_ET"], pre_sort_ascending=False,
                                  sort_columns=[sort_on], sort_ascending=sort_ascending, addColumns={"ObjType": 5}),
                    ObjectProfile("EFlowNeutralHadron", 100, pre_sort_columns=["PT_ET"], pre_sort_ascending=False,
                                  sort_columns=[sort_on], sort_ascending=sort_ascending, addColumns={"ObjType": 6}),
                    ObjectProfile("EFlowTrack", 100, pre_sort_columns=["PT_ET"], pre_sort_ascending=False,
                                  sort_columns=[sort_on], sort_ascending=sort_ascending, addColumns={"ObjType": 7})]

                #resolveProfileMaxes(object_profiles, ldp)
                print(archive_dir, (num_val, num_train), num_val+num_train, \
                                              object_profiles, ldp, observ_types,)
                dps, l = getGensDefaultFormat(archive_dir, (num_val, num_train), num_val+num_train, \
                                              object_profiles, ldp, observ_types,
                                              single_list=single_list, sort_columns=[sort_on], sort_ascending=sort_ascending,
                                              batch_size=batch_size, megabytes=100,
                                              verbose=0)

                dependencies = batchAssertArchived(dps, 4)
                val, _num_val = l[0]
                train, _num_train = l[1]
                max_q_size = l[2]

                val_dps = val.args[0]
                train_dps = train.args[0]

                for name in ['LSTM']:
                    for optimizer in optimizer_options:
                        for depth in [1]:
                            for activation in ['tanh']:
                                for lstm_dropout in [0.0]:
                                    for dropout in [0.0]:
                                        activation_name = activation if isinstance(activation, str) \
                                            else activation.__name__

                                        model = genModel(name, object_profiles, len(labels), depth,vecsize, lstm_activation=activation,
                                                         lstm_dropout=lstm_dropout,dropout=dropout, output_activation=output_activation,
                                                        single_list=single_list)



                                        trial = MPI_KerasTrial(archive_dir, name=name, model=model, workers=workers)
                                        # trial = KerasTrial(archive_dir, name=name, model=model)

                                        trial.setTrain(train_procedure=train_dps,
                                                       samples_per_epoch=_num_train
                                                       )
                                        trial.setValidation(val_procedure=val_dps,
                                                            nb_val_samples=_num_val)

                                        trial.setCompilation(loss=loss,
                                                             optimizer=optimizer,
                                                             metrics=['accuracy']
                                                             )

                                        trial.setFit_Generator(
                                            nb_epoch=epochs,
                                            callbacks=[earlyStopping],
                                            max_q_size=max_q_size)
                                        trial.write()

                                        trial_tups.append((trial, None, None, dependencies))

                                        trial.to_record({"labels": labels,
                                                         "depth": depth,
                                                         "sort_on": sort_on,
                                                         "sort_ascending": sort_ascending,
                                                         "activation": activation_name,
                                                         "dropout": dropout,
                                                         "lstm_dropout": lstm_dropout,
                                                         "query": None,
                                                         "patience": patience,
                                                         "single_list" : single_list,
                                                         #"useObjTypeColumn": True,
                                                         "output_activation": output_activation
                                                         # "Non_MPI" :True
                                                         })
    # trial_tups[0][0].summary()
    # trial_tups[0][0].execute()
    for tup in trial_tups:
        tup[0].summary()
    for tup in trial_tups:
        tup[0].execute()
    # batchExecuteAndTestTrials(trial_tups)

if __name__ == '__main__':
    argv = sys.argv
    runTrials(argv[1], int(argv[2]))