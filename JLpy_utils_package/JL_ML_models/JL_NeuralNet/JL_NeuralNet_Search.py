from __init__ import *

import sklearn, sklearn.model_selection
try:
    import dill
except ImportError:
    sys.exit("""You need dill. run: '!pip install dill'""")

import tensorflow.keras as keras
import time

def run_single_cv_fit(X_train, y_train,
                       X_test, y_test,
                       train_idx, val_idx,
                       model,
                       batch_size, 
                       epochs,
                       callbacks,
                       scoring,
                       verbose=0):
    
    X_train_val, X_val = X_train[train_idx], X_train[val_idx]
    y_train_val, y_val = y_train[train_idx], y_train[val_idx]
    
    #fit the model
    history = model.fit(x=X_train_val, 
                        y=y_train_val, 
                        validation_data=(X_val, y_val),
                        batch_size=batch_size, 
                        epochs = epochs, 
                        verbose= verbose, 
                        callbacks = callbacks)
    metrics_dict = {}
    for key in history.history.keys():
        if key!='lr':
            metrics_dict[key] = history.history[key][-1]

    Score = metrics_dict['val_'+scoring['metric']]
                      
    return Score
      

class GridSearchCV:
    
    def __init__(self, 
                 compiler, 
                   param_grid, 
                   callbacks = [keras.callbacks.EarlyStopping(monitor='val_loss', patience =10)],
                   scoring = {'metric': 'loss', 'maximize':False},
                   batch_size = 32,
                   epochs = 100,
                   cv='warn', 
                   path_report_folder = os.path.abspath('.'),
                   verbose=1):
        
        self.param_grid = param_grid
        self.compiler = compiler
        self.cv = cv
        self.verbose = verbose
        self.param_grid = param_grid
        self.callbacks = callbacks
        self.batch_size = batch_size
        self.epochs = epochs
        self.scoring = scoring
        
        #check assertions
        assert(type(self.scoring)==dict), 'scoring must be a dictionary with a "metric" and "maximize" key'
        
        #append to cv_Scores list
        if self.scoring['metric'] == None: #use validation loss as the score if history 
            self.scoring['metric'] = 'loss'
            
        if self.scoring['metric'] != 'loss':   
            #update param_grid if scoring metrics not already in param grid
            if scoring['metric'] not in self.param_grid['metrics'][0]:
                self.param_grid['metrics'][0].append(scoring['metric'])
        
        #ensure the report folder has consistant nomenclature at its root
        root_name = 'GridSearchCV'
        if root_name not in path_report_folder:
            path_report_folder = os.path.join(path_report_folder,root_name)
        self.path_report_folder = path_report_folder
        
        #build report folder
        if os.path.isdir(self.path_report_folder)==False:
            os.makedirs(self.path_report_folder)
        
        #save the settings to the report folder
        file = open(os.path.join(self.path_report_folder,'compiler.dill'),'wb')
        dill.dump(self.compiler, file)
        file.close()
        
#         file = open(os.path.join(self.path_report_folder,'callbacks.dill'),'wb')
#         dill.dump(self.callbacks, file)
#         file.close()
        
        batch_size_epochs_cv_params = {'batch_size':self.batch_size,
                                      'epochs':self.epochs,
                                      'cv':self.cv}
        file = open(os.path.join(self.path_report_folder,'batch_size_epochs_cv_params.dill'),'wb')
        dill.dump(batch_size_epochs_cv_params, file)
        file.close()
        
        
    def Kfold(self, X, y, n_splits = 5, stratified = False ):
        """
        Build train - validation index generator for K fold splits
        """
        
        
        
        if len(y.shape)>1:
            if y.shape[1]>1: #if y is one hot encoded
                y_flat = np.zeros((y.shape[0],1))

                encoding_idx = 0
                for c in range(y.shape[1]):
                    y_flat[y[:,c]==1] = encoding_idx
                    encoding_idx+=1
        else: y_flat = y
        
        if stratified:
            kf = sklearn.model_selection.StratifiedKFold(n_splits = n_splits, shuffle=True)
        else:
            kf = sklearn.model_selection.KFold(n_splits=n_splits, shuffle=True)
        
        kf_Xy_split_idx_gen = kf.split(X)
        
        return kf_Xy_split_idx_gen 
    
    def ParameterGrid(self, param_grid):
        return list(sklearn.model_selection.ParameterGrid(param_grid))
    
    def fit(self, X_train, y_train, X_test, y_test):
        
        X_train = np.array(X_train)
        y_train = np.array(y_train)
        X_test = np.array(X_test)
        y_test = np.array(y_test)
        
        #build parameter grid list
        self.ParameterGrid_dict = {}
        self.ParameterGrid_dict['params'] = self.ParameterGrid(self.param_grid)
        
        if self.verbose >=1:
            print('running', self.cv, 'fold cross validation on',len(self.ParameterGrid_dict['params']),'hyperparemter combinations, for a total of',self.cv*len(self.ParameterGrid_dict['params']),'models')
            print('Scoring using',self.scoring)
        
        cv_verbosity = self.verbose
        if cv_verbosity==1: cv_verbosity = 0
            
        self.ParameterGrid_dict[self.scoring['metric']] = np.zeros((len(self.ParameterGrid_dict['params'])))
        
        #save to report folder
        file = open(os.path.join(self.path_report_folder,'ParameterGrid_dict.dill'),'wb')
        dill.dump(self.ParameterGrid_dict, file)
        file.close()
        
        #run grid search
        p=0
        time_cv_list = []
        for params in self.ParameterGrid_dict['params']:
            if self.verbose >=1:
                print('\tParameter sweep progress:',
                      round((p+1)/len(self.ParameterGrid_dict['params'])*100,6), 
                      '(total time (mins):', 
                      round(np.sum(time_cv_list),2),'of ~',
                      round(np.median(time_cv_list)*len(self.ParameterGrid_dict['params']),2),')',
                      end='\r')
            
            #build the model
            model = self.compiler(**params)
            if self.verbose >=4:
                model.summary()
            
            if self.verbose>=3:
                print('\tn_params:',model.count_params())
                
            #get cv split generator
            kf_Xy_split_idx_gen  = self.Kfold(X_train, y_train, self.cv)

            cv_Scores = []
            time_cv = time.time() #total cv training time
            c=0
            for train_idx, val_idx in kf_Xy_split_idx_gen:
                
                time_train = time.time()
                Score = run_single_cv_fit(X_train, y_train,
                                          X_test, y_test,
                                          train_idx, val_idx,
                                          model,
                                          self.batch_size, 
                                          self.epochs,
                                          self.callbacks,
                                          self.scoring,
                                          verbose=cv_verbosity)
                if self.verbose>=3:
                    print('\t\tScore:',Score) 
                cv_Scores.append(Score)
                time_train = (time.time() - time_train)/60
                
                if self.verbose>=1:
                    print('\t\tcv Progress:',round((c+1)/self.cv*100,3),
                          '(train time (mins):',round(time_train,2),')\t\t\t',end='\r')
                c+=1
                
            
            time_cv = (time.time() - time_cv)/60
            time_cv_list.append(time_cv)
            
            #eval avg. score for all cvs
            Score = np.mean(cv_Scores)
            if self.verbose>=2:
                print('\tcv Score:',Score,' (cv time (mins):',round(time_cv,2),')\t\t\t')
            self.ParameterGrid_dict[self.scoring['metric']][p] = Score
            
            #save to report folder
            file = open(os.path.join(self.path_report_folder,'ParameterGrid_dict.dill'),'wb')
            dill.dump(self.ParameterGrid_dict, file)
            file.close()               
                                               
            p+=1
        
        #determine best score
        if self.scoring['maximize']:
            self.best_score_ = np.max(self.ParameterGrid_dict[self.scoring['metric']])
        else:
            self.best_score_ = np.min(self.ParameterGrid_dict[self.scoring['metric']])
            
        #find idx of best score
        best_idx = np.where(np.array(self.ParameterGrid_dict[self.scoring['metric']]) == self.best_score_)[0][0]
        
        #fetch best parameters
        self.best_params_ = self.ParameterGrid_dict['params'][best_idx]
        file = open(os.path.join(self.path_report_folder,'best_params_.dill'),'wb')
        dill.dump(self.best_params_, file)
        file.close() 
        
        if self.verbose >=1:
            print('best_score_:',self.best_score_,'         ')
            print('best_params_:')
            display(self.best_params_)
        
        #fetch best model
        if self.verbose >=2:
            print('Fitting best estimator...')
        model = self.compiler(**self.best_params_)
        model.fit(x=X_train, y=y_train,
                  validation_data=(X_test, y_test),
                batch_size=self.batch_size, 
                epochs = self.epochs, 
                verbose= cv_verbosity, 
                callbacks = self.callbacks)
        self.best_estimator_ = model
        
        try:
            self.best_estimator_.save(os.path.join(self.path_report_folder,'best_estimator_.h5')) 
        except:
            print('An error was raised while saving best_estimator_, consider manual saving the model outside the GridSearchCV.fit method')
        
        if self.verbose >=2:
            print('...Finished')
        
            