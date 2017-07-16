"""基于HDF文件的数据库"""

import pandas as pd
import os
import shutil
from utils.datetime_func import Datetime2DateStr, DateStr2Datetime

class H5DB(object):
    def __init__(self, data_path):
        self.data_path = data_path
        self.feather_data_path = os.path.abspath(data_path+'/../feather')
        self.data_dict = None
        self._update_info()
    
    def _update_info(self):
        factor_list = []
        
        def update_factors(path, root='/'):
            for file in os.listdir(path):
                file_path = os.path.join(path, file)
                if os.path.isdir(file_path):
                    update_factors(file_path, root=root+'%s/' % file)
                else:
                    if file[-3:] == '.h5':
                        panel = pd.read_hdf(file_path, file[:-3])
                        min_date = Datetime2DateStr(panel.major_axis.min())
                        max_date = Datetime2DateStr(panel.major_axis.max())
                        factor_list.append([root, file[:-3], min_date, max_date])
                    else:
                        pass
        update_factors(self.data_path)
        self.data_dict = pd.DataFrame(
            factor_list, columns=['path', 'name', 'min_date', 'max_date'])
    
    def set_data_path(self, path):
        self.data_path = path
        self._update_info()
    
    #---------------------------因子管理---------------------------------------
    # 查看因子是否存在
    def check_factor_exists(self, factor_name, factor_dir='/'):
        return factor_name in self.data_dict[self.data_dict['path']==factor_dir]['name'].values

    # 删除因子
    def delete_factor(self, factor_name, factor_dir='/'):
        factor_path = self.abs_factor_path(factor_dir, factor_name)
        try:
            os.remove(factor_path)
        except Exception as e:
            print(e)
            pass
    
    # 重命名因子
    def rename_factor(self, old_name, new_name, factor_dir):
        factor_path = self.abs_factor_path(factor_dir, old_name)
        factor_data = pd.read_hdf(factor_path, old_name)
        temp_factor_path = self.abs_factor_path(factor_dir, new_name)
        factor_data.to_hdf(temp_factor_path, new_name, complevel=9, complib='blosc')
        self.delete_factor(old_name, factor_dir)

    #新建因子文件夹
    def create_factor_dir(self, factor_dir):
        if not os.path.isdir(self.data_path+factor_dir):
            os.makedirs(self.data_path+factor_dir)
    
    #因子的时间区间
    def get_date_range(self, factor_name, factor_path):
        return tuple(self.data_dict.loc[(self.data_dict['path']==factor_path) &
                              (self.data_dict['name']==factor_name), ['min_date', 'max_date']].stack())

    #--------------------------数据管理-------------------------------------------

    def load_factor(self, factor_name, factor_dir=None, dates=None, ids=None, idx=None):
        factor_path = self.abs_factor_path(factor_dir, factor_name)
        panel = pd.read_hdf(factor_path, factor_name)
        if idx is not None:
            return panel.to_frame().rename_axis(['date','IDs']).loc[idx,:]
        if (ids is not None) and (not isinstance(ids, list)):
            ids = [ids]
        if dates is None and ids is None:
            df = panel.to_frame()
            return df
        elif dates is None:
            df = panel.ix[factor_name, :, ids].stack().to_frame()
            df.index.names = ['date', 'IDs']
            df.columns = [factor_name]            
            return df
        elif ids is None:
            df = panel.ix[factor_name, pd.DatetimeIndex(dates), :].stack().to_frame()
            df.index.names = ['date', 'IDs']
            df.columns = [factor_name]              
            return df
        else:
            df = panel.ix[factor_name, pd.DatetimeIndex(dates), ids].stack().to_frame()
            df.index.names = ['date', 'IDs']
            df.columns = [factor_name]              
            return df
    
    def load_factors(self, factor_names_dict, dates=None, ids=None):
        _l = []
        for factor_path, factor_names in factor_names_dict.items():
            for factor_name in factor_names:
                df = self.load_factor(factor_name, factor_dir=factor_path, dates=dates, ids=ids)
                _l.append(df)
        return pd.concat(_l, axis=1)
    
    def save_factor(self, factor_data, factor_dir, if_exists='append'):
        """往数据库中写数据
        数据格式：DataFrame(index=[date,IDs],columns=data)
        """
        if factor_data.index.nlevels == 1:
            if isinstance(factor_data.index, pd.DatetimeIndex):
                factor_data['IDs'] = '111111'
                factor_data.set_index('IDs', append=True, inplace=True)
            else:
                factor_data['date'] = DateStr2Datetime('19000101')
                factor_data.set_index('date', append=True, inplace=True)
    
        self.create_factor_dir(factor_dir)
        for column in factor_data.columns:
            factor_path = self.abs_factor_path(factor_dir, column)
            if not self.check_factor_exists(column, factor_dir):
                factor_data[[column]].to_panel().to_hdf(factor_path, column, complevel=9, complib='blosc')
            elif if_exists == 'append':
                old_panel = pd.read_hdf(factor_path, column)
                new_frame = old_panel.to_frame().append(factor_data[[column]])
                new_panel = new_frame[~new_frame.index.duplicated(keep='last')].to_panel()
                available_name = self.get_available_factor_name(column, factor_dir)
                new_panel.to_hdf(
                    self.abs_factor_path(factor_dir, available_name), available_name, complevel=9, complib='blosc')
                self.delete_factor(column, factor_dir)
                self.rename_factor(available_name, column, factor_dir)
            elif if_exists == 'replace':
                self.delete_factor(column, factor_dir)
                factor_data[[column]].to_panel().to_hdf(factor_path, column, complevel=9, complib='blosc')
            else:
                self._update_info()
                raise KeyError("please make sure if_exists is valide")
        self._update_info()
    
    def to_feather(self, factor_name, factor_dir):
        """将某一个因子转换成feather格式，便于跨平台使用"""
        data = self.load_factor(factor_name, factor_dir).reset_index()
        data.to_feather(self.feather_data_path+factor_dir+factor_name+'.feather')
    #-------------------------工具函数-------------------------------------------
    def abs_factor_path(self, factor_path, factor_name):
        return self.data_path + os.path.join(factor_path, factor_name+'.h5')
    
    def get_available_factor_name(self, factor_name, factor_path):
        i = 2
        while os.path.isfile(self.abs_factor_path(factor_path, factor_name+str(i))):
            i += 1
        return factor_name + str(i)
    